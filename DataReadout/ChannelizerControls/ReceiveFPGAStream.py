import clTools
import datetime, os, pickle, socket, struct, time, glob
import numpy as np
class ReceiveFPGAStream():
    packetLabels = ['baseline','wvl','timestamp','ycoord','xcoord','usec']
    def __init__(self,port=50000,host='',timeoutSeconds=3, iSecond=None, doFastForward=True):
        self.port = port
        self.timeoutSeconds = timeoutSeconds
        print "ReceiveFPGAStream.__init__:  port=",port
        if self.port == "/mnt/ramdisk/frame":
            self.fromSocket = False
            self.iFrame = None
        elif self.port == "/mnt/ramdisk/frames":
            self.fromSocket = False
            self.iSecond = iSecond
            self.i0 = None
        else:
            self.fromSocket = True
            self.s = socket.socket(socket.AF_INET,
                                   socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.s.settimeout(self.timeoutSeconds)
            bufferSize = 335544320
            self.s.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,
                              bufferSize)
            self.s.bind(('',port))

    def read(self):
        if self.fromSocket:
            try:
                data = self.s.recv(4096)
            except socket.timeout:
                data = None
        else:
            if self.port == "/mnt/ramdisk/frame":
                if self.iFrame is None:
                    self.fastForward()
                data = self.readFromRamdisk()
                self.iFrame += 1
            else:
                if self.iSecond == None:
                    self.fastForward()
                    self.iRecord = None
                if self.i0 == None:
                    self.loadRecordsFromFrames()
                if self.records is None:
                    self.i0 = None
                    return None
                if self.i0 >= len(self.records):
                    self.loadRecordsFromFrames()
                if self.records is not None:
                    # The next two bytes are the length of the next frame
                    nbytes = struct.unpack('<I',
                                           self.records[self.i0:self.i0+4])[0]
                    i1 = self.i0+8+nbytes
                    data = self.records[self.i0+8:i1]
                    self.i0 = i1
                else:
                    data = None
        return data
    def loadRecordsFromFrames(self):
        self.i0 = 0
        self.records = self.readFromRamdisk()
        if self.records is not None:
            self.iSecond += 1
    def whereAmI(self):
        if not self.fromSocket:
            fn = max([ f for f in os.listdir('/mnt/ramdisk') if f.startswith('frame')])
            if self.port.endswith("frame"):
                iFrameNewest = int(fn[5:14],10)
                lag = iFrameNewest - self.iFrame
            else:
                iSecondNewest = int(fn[6:16],10)
                lag = iSecondNewest - self.iSecond
                print "hello from whereAmI:  iSecondNewest=",iSecondNewest, "self.iSecond=",self.iSecond
        else:
            lag = 0
        return lag
        
    def readFromRamdisk(self, iFrameOrSecond=None):
        if self.port == "/mnt/ramdisk/frame":
            if iFrameOrSecond is None:
                iFrameOrSecond = self.iFrame
            fn = "/mnt/ramdisk/frame%09d.bin"%iFrameOrSecond
            # wait for the file to appear
            for i in range(timeoutSeconds):
                if os.path.isfile(fn):
                    with open(fn, mode='rb') as file:
                        data = file.read()
                    return data
                time.sleep(1)
            # timed out
            return None
        else:
            if iFrameOrSecond is None:
                if self.iSecond is None:
                    # nothing found on /mnt/ramdisk
                    time.sleep(self.timeoutSeconds)
                    return None
                iFrameOrSecond = self.iSecond
            
            fn = "/mnt/ramdisk/frames%10d.bin"%iFrameOrSecond
            # wait for the file to appear
            print "ReceiveFPGAStream:  wait for fn=",fn
            for i in range(self.timeoutSeconds):
                if os.path.isfile(fn):
                    with open(fn, mode='rb') as file:
                        data = file.read()
                    return data
                time.sleep(1)
            # timed out
            return None
            
    def fastForward(self):
        if self.port.endswith("frame"):
            fileList = [ f for f in os.listdir('/mnt/ramdisk') if f.startswith('frame')]
            fn = max(fileList)
            if len(fileList) > 0:
                self.iFrame = int(fn[5:14],10)
        else:
            fileList = [ f for f in os.listdir('/mnt/ramdisk') if f.startswith('frames')]
            if len(fileList) > 0:
                fn = max(fileList)
                self.iSecond = int(fn[6:16],10)
            
    @staticmethod
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
            retval = {"tag":tag,"roach":roach, "frame":frame,
                      "starttime":starttime, "valid":True}
            nPacket = (len(d)/8) - 1
            packets = np.empty((nPacket,6),dtype=np.int32)
            retval['packets'] = packets

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
                packets[iPacket,:] = np.array(l,dtype=np.uint32)
        return retval
    @staticmethod
    def unpackOneFramesFile(ffn):
        print "begin ReceiveFPGAStream.unpackOneFrameFile ffn=",ffn
        with open(ffn,'rb') as file:
            data = file.read()
        i0 = 0
        times = {}
        phases = {}
        baselines = {}
        while(i0 < len(data)):
            nbytes = struct.unpack("<I",data[i0:i0+4])[0]
            i0 += 8
            i1 = i0+nbytes
            packet = data[i0:i1]
            unpacked = ReceiveFPGAStream.unpack(packet)
            p = unpacked['packets']
            nPhotons = p.shape[0]
            t0Frame = unpacked['starttime']*0.5e-3
            for iPhoton in range(nPhotons):
                channel = p[iPhoton,4]
                if channel < 511:
                    if channel not in times:
                        times[channel] = []
                        phases[channel] = []
                        baselines[channel] = []
                    usec = 1e-6*p[iPhoton,2]
                    seconds = t0Frame + usec
                    times[channel].append(seconds)
                    # we are using the "wvl" to report phase
                    phase = p[iPhoton,1] 
                    phases[channel].append(phase)
                    baseline = p[iPhoton,0]
                    baselines[channel].append(baseline)
            i0 = i1
        for key in times.keys():
            times[key] = np.array(times[key])
            baselines[key] = np.array(baselines[key])
            baselines[key] = clTools.phasesIntToDouble(baselines[key],
                                                       nBitsPerPhase=17,
                                                       binPtPhase=14)
            phases[key] = np.array(phases[key])
            phases[key] = clTools.phasesIntToDouble(phases[key],
                                                    nBitsPerPhase=18,
                                                    binPtPhase=15)
        return {"ffn":ffn,"times":times,"baselines":baselines,"phases":phases}
    
    @staticmethod
    def getLastFrame():
        list_of_files = glob.glob('/mnt/ramdisk/*.bin')
        latest_file = max(list_of_files, key=os.path.getctime)
        print latest_file
        return ReceiveFPGAStream.unpackOneFramesFile(latest_file)

    

def test(fn):
    print "test",fn
    with open(fn,'rb') as f:
        d = f.read()
    f.close()

    
    ind = 0
    i0s = []
    i1s = []

    while True:
        try:
            nbytes = ord(d[ind])+256*ord(d[ind+1])
            nbytes = struct.unpack('<I', d[ind:ind+4])[0]
            print "i, nbytes = ",len(i0s),nbytes
            i0s.append(ind+8)
            i1s.append(ind+8+nbytes)
            ind += 8 + nbytes
        except IndexError:
            break
    for i0,i1 in zip(i0s,i1s):
        rv = ReceiveFPGAStream.unpack(d[i0:i1])
        print rv['roach'],rv['frame']
    return d

if __name__ == "__main__":
    ffn = "frames1558032100.bin"
    t0 = datetime.datetime.now()
    rv = ReceiveFPGAStream.unpackOneFramesFile(ffn)
    t1 = datetime.datetime.now()
    print "seconds=",(t1-t0).total_seconds()
