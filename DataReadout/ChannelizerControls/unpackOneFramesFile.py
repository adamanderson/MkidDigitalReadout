from numba import jit
import clTools
import datetime, struct
import numpy as np
import array

#@jit(nopython=True)
def unpackOneFramesFile(ffn):
    with open(ffn,'rb') as file:
        data = file.read()
    return unpackData(data)

def unpackData(data):
    frames = []
    i0 = 0
    while(True):
        nbytes = ord(data[i0])+256*ord(data[i0+1])
        i0 += 8
        i1 = i0+nbytes
        frame = data[i0:i1]
        frames.append(frame)
        if i1 >= len(data):
            break
        i0 = i1
    return unpackFrames(frames)

#@jit(nopython=True)
def unpackFrames(frames):
    i0 = 0
    times = []
    phases = []
    baselines = []
    channels = []
    syncTimes = []
    syncChannels = []
    nLoop = 0
    for frame in frames:
        t,p,b,c,st,sc = unpackFrame(frame)
        times += t
        phases += p
        baselines += b
        channels += c
        syncTimes += st
        syncChannels += sc
    times = np.array(times)
    baselines = np.array(baselines)
    baselines = clTools.phasesIntToDouble(baselines,
                                               nBitsPerPhase=17,
                                               binPtPhase=14)
    phases = np.array(phases)
    phases = clTools.phasesIntToDouble(phases,
                                            nBitsPerPhase=18,
                                            binPtPhase=15)
    channels = np.array(channels)
    syncTimes = np.array(syncTimes)
    syncChannels = np.array(syncChannels)
    return {"times":times,"baselines":baselines,
            "phases":phases,"channels":channels,
            "syncTimes":syncTimes,"syncChannels":syncChannels
    }
    #return (times,baselines,phases,channels)

#@jit(nopython=True)
def unpackFrame(frame):
    times = []
    phases = []
    baselines = []
    channels = []
    syncTimes = []
    syncChannels = []
    #unpacked = unpack(packet)
    tag,roach,frame,starttime,packets = unpack(frame)
    p = packets
    nPhotons = len(p)
    t0Frame = starttime*0.5e-3
    #print "frame,t0Frame, starttime = %5d %.4f  %d"%(frame, t0Frame, starttime)
    for iPhoton in range(nPhotons):
        channel = p[iPhoton][4]
        if channel < 511:
            tstamp = p[iPhoton][2]
            if tstamp < 511:
                usec = 1e-6*p[iPhoton][2]
                seconds = t0Frame + usec
                channels.append(channel)
                times.append(seconds)
                # we are using the "wvl" to report phase
                phase = p[iPhoton][1] 
                phases.append(phase)
                baseline = p[iPhoton][0]
                baselines.append(baseline)
            else:
                syncTimes.append(t0Frame)
                syncChannels.append(channel)
    return times,phases,baselines,channels,syncTimes,syncChannels


#@jit
def unpack(d, frameOnly=False):
    """
    Return a dictionary of tag, roach, frame, starttime, and packets.

    packets has shape (100,5) where the 5 variables per datapacket are, 
    in order:
      baseline, wvl, timestamp, ycoord, xcoord.  
    (Note the order of y and x!)

    This is in the list ReceiveFPGAStream.packetLabels, defined above. 

    Simply assume that d starts with the value 255 and raise an error 
    if it does not.

    The first 8 bytes of d are a hdrpacket, 
    described by the structure hdrpacket in PacketMaster2.c

    struct hdrpacket {
        unsigned long timestamp:36; # The 36 bit header timestamp is the 
                                    # number of half ms since some reference time
        unsigned int frame:12;      # incrementing frame number
        unsigned int roach:8;       # the roach number, for example, 100
        unsigned int start:8;       # always 255
    }__attribute__((packed));;

    This is followed by 100 data packets, each one is 8 bytes, 
    described by the structure datapacket in PacketMaster2.c

    struct datapacket {
        unsigned int baseline:17;  # phase baseline computed by the SVF filter.  
                                   #This is kept for debugging purposes
        unsigned int wvl:18;       # signed(2s complement) fixed point
                                   # binary number with 18 bits total,  
                                   # and 15 bits after the binary point
        unsigned int timestamp:9;  # number of us since the last half ms
        unsigned int ycoord:10;    # y pixel location in the array
        unsigned int xcoord:10;    # x pixel location in the array
    }__attribute__((packed));;

    """
    if d is None:
        rv = {"valid":False}
        return rv

    if ord(d[0]) != 255:
        raise ValueError("It should be 255 but ord(d[0])=%d"%ord(d[0]))
    a = d[:8]
    #ss = struct.unpack('<Q',a)[0] 
    ss = struct.unpack('>Q',a)[0] # this byte order worked on April 22, 2019
    frame    = (ss & 0x0000FFF000000000) >> 36
    if frameOnly:
        retval = {"frame":frame, "valid":True}
    else:
        tag      = (ss & 0xFF00000000000000) >> 56
        roach    = (ss & 0x00FF000000000000) >> 48
        starttime = ss & 0x0000000FFFFFFFFF
        nPacket = (len(d)/8) - 1
        #packets = np.empty((nPacket,6),dtype=np.int32)
        packets = []
 
        timestamp0 = None
        for iPacket in range(0,nPacket):
            i1 = 8*(iPacket+1)
            a = d[i1:i1+8]
            ss = struct.unpack('>Q',a)[0]
            baseline = ss & ((2**17)-1)
            ss = ss >> 17
            wvl = ss & ((2**18)-1)
            ss = ss >> 18
            timestamp = ss & ((2**9)-1)
            if timestamp0 is None:
                timestamp0 = timestamp
                timestampWrapOffset = 0
                timestampPrevious = timestamp
            if timestampPrevious > timestamp:
                timestampWrapOffset += 500 # Based on looking at firmware, this is not 512.
            #usec = timestamp - timestamp0 + timestampWrapOffset
            usec = timestamp + timestampWrapOffset
            timestampPrevious = timestamp
            ss = ss >> 9
            ycoord = ss & ((2**10)-1)
            ss = ss >> 10
            xcoord = ss & ((2**10)-1)
            l = [baseline,wvl,timestamp,ycoord,xcoord,usec]
            packets.append(l)
            #packets[iPacket,:] = np.array(l,dtype=np.uint32)
#        retval = {"tag":tag,"roach":roach, "frame":frame,
#                  "starttime":starttime, "valid":True}
    return tag,roach,frame,starttime,packets




if __name__ == "__main__":
    ffn = "frames1558032100.bin"
    t0 = datetime.datetime.now()
    rv = unpackOneFramesFile(ffn)
    t1 = datetime.datetime.now()
    print "time ",(t1-t0).total_seconds()
    #t0 = datetime.datetime.now()
    #rv = unpackOneFramesFile(ffn)
    #t1 = datetime.datetime.now()
    #print "time ",(t1-t0).total_seconds()
