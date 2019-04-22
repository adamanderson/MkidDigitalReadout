import pickle, socket, struct
import numpy as np
class ReceiveFPGAStream():
    def __init__(self,port=50000,host='',timeoutSeconds=3):
        self.port = port
        self.host = ''
        self.timeoutSeconds = timeoutSeconds
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.s.settimeout(self.timeoutSeconds)
        self.s.bind((self.host,self.port))
        print "done initializing socket"
        #self.s.listen(1)
        #print "after call s.listen(1)"
        #self.conn, self.addr = self.s.accept()
        #print "after accept:  conn,addr =",self.conn, self.addr
        
    def read(self):
        try:
            data = self.s.recv(1024)
        except socket.timeout:
            data = None
        return data

    def unpack(self,d):
        """
        Return a dictionary of tag, roach, frame, starttime, and packets.

        packets has shape (100,5) where the 5 variables per datapacket are, in order:
          baseline, wvl, timestamp, ycoord, xcoord.  (Note the order of y and x!)

        Simply assume that d starts with the value 255 and raise an error if it does not.

The first 8 bytes of d are a hdrpacket, 
described by the structure hdrpacket in PacketMaster2.c

struct hdrpacket {
    unsigned long timestamp:36;
    unsigned int frame:12;
    unsigned int roach:8;
    unsigned int start:8;
}__attribute__((packed));;

This is followed by 100 data packets, each one is 8 bytes, 
described by the structurn datapacket in PacketMaster2.c

struct datapacket {
    unsigned int baseline:17;
    unsigned int wvl:18;
    unsigned int timestamp:9;
    unsigned int ycoord:10;
    unsigned int xcoord:10;
}__attribute__((packed));;

"""
        
        if ord(data[0]) != 255:
            raise ValueError("It should be 255 but ord(data[0])=%d"%ord(data[0]))
        a = d[:8]
        #ss = struct.unpack('<Q',a)[0] 
        ss = struct.unpack('>Q',a)[0] # this byte order worked on April 22, 2019
        tag = (ss & 0xFF00000000000000) >> 56
        roach = (ss & 0xFF000000000000) >> 48
        frame = ((ss & 0xFFF000000000) >> 36 )
        starttime = ss & 0xFFFFFFFFF
        retval = {"tag":tag,"roach":roach, "frame":frame, "starttime":starttime}
        nPacket = (len(d)/8) - 1
        packets = np.empty((nPacket,5),dtype=np.int32)
        retval['packets'] = packets
        for iPacket in range(0,100):
            i1 = 8*(iPacket+1)
            a = d[i1:i1+8]
            ss = struct.unpack('>Q',a)[0]
            if iPacket < 3:
                baseline = ss & ((2**17)-1)
                ss = ss >> 17
                wvl = ss & ((2**18)-1)
                ss = ss >> 18
                timestamp = ss & ((2**9)-1)
                ss = ss >> 9
                ycoord = ss & ((2**10)-1)
                ss = ss >> 10
                xcoord = ss & ((2**10)-1)
                packets[iPacket,:] = np.array([baseline,wvl,timestamp,ycoord,xcoord],dtype=np.int32)
        return retval
        
if __name__ == "__main__":
    rfs = ReceiveFPGAStream()
    for i in range(3000):
        data = rfs.read()
        if data is None:
            print "timedout"
        else:
            rv = rfs.unpack(data)
            print rv['frame']
            for i in range(3):
                baseline,wvl,timestamp,ycoord,xcoord = rv['packets'][i]
                print i, "wvl=",wvl, "timestamp=",timestamp
