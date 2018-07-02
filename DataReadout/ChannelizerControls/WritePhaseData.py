""" 
Write phase data to a file in either ASCII or HDF5 format.

called as:
 wp=WritePhase.writePhase(filename,format,freqChan,freqs,duration,data)
 wp.Write()
 
filename: file name, default "test"
format:  file format,"ascii" or "hdf5". Data is written to filename.dat or filename.h5 depending on the format.
freqChan: channel number of the frequency
freqs: array of frequencies in use (obtained from freqs=rchc.roachController.freqChannels )
duration: durationto collect data
data: Roach data array  (obtained  from data = rchc.roachController.takePhaseStreamDataOfFreqChannel(
        freqChan=freqChan, duration=duration, hostIP=hostIP, fabric_port=port) )
"""

import h5py as h5 
import numpy as np
import datetime
import os

class writePhaseData():
    def __init__(self,fileName,fFormat,freqChan,frequencies,duration,data):
        self.fileName = fileName
        self.freqChan = freqChan
        self.duration=duration
        self.fFormat=fFormat.strip()
        self.data = data
        self.freqs = frequencies

        if not (self.fFormat is "ascii" or self.fFormat is "hdf5"):
	        print "ERROR: wrong format type, use format: \"ascii\" or \"hdf5\""
	        
		 

    
    def writeAscii(self):
        dtime=str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")) 
        print dtime
        sdtime="Time : "+dtime +"\n" 
        sdur = "Duration : %6.3fs\n"%self.duration
        schan= "Frequency Channel: %d \n"%self.freqChan	
        filename=self.fileName+".dat"	
        print "writing to file", filename, " time ", dtime
        nfile = open(filename,'wb')  
        nfile.write(sdtime)
        nfile.write(sdur)
        nfile.write(schan)
        nfile.write("Frequencies: \n")
        np.savetxt(nfile, self.freqs)
        nfile.write("data \n")	     
        np.savetxt(nfile, self.data)


    def writeHDF5(self):
        dtime=str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")) 

        filename=self.fileName+".h5"
        print "writing to file ",filename, " time ", dtime
        if os.path.exists(filename):
            try:
  		       fileh=h5.File(filename,"w")  
            except IOError:
               print "Could not open file! close ", filename		
        else:
            fileh=h5.File(filename,"w")

        grp = fileh.create_group('/Phase Data')
        grp['data']=self.data
        dset=grp['data']
        dset.attrs['time']=dtime
        dset.attrs['duration']=self.duration
        dset.attrs['frequency channel']=self.freqChan
        dset.attrs['frequencies']=self.freqs
        fileh.flush()
        fileh.close()


    def Write(self):
        if self.fFormat is "ascii":
            self.writeAscii()
        elif self.fFormat is "hdf5":
            self.writeHDF5()		
    pass


class ReadPhaseData():
    def __init__(self):
        pass

    def readFile(self,fileName):
        type=str(fileName[fileName.index(".")+1:])
        type=type.strip()

        if type=="dat":
	         x=self.readAscii(fileName)
           
        elif type=="h5":
            x=self.readHDF5(fileName)
            
        else:
            print "wrong file extension type"
            x={}
        return x


    def readAscii(self,fileName):
        filen=fileName.strip()
        fileh=open(filen,"r")
        lines=fileh.readlines()

        line1=lines[0].split()
        pdate=line1[2]
        ptime=line1[3]

        line2=lines[1].split()

        duration=float(line2[2][:-1])

        line3=lines[2].split()
        freqch=int(line3[2])

        dindex=lines.index("data \n")
        freqlist=lines[4:dindex]
        freqs=np.float_(freqlist)	

        datalist=lines[dindex+1:]
        data=np.float_(datalist)

        phasedata={'date': pdate,'time':ptime, 'duration':duration,'freqency channel':freqch, 'frequencies':freqs,'data':data}
		
        return  phasedata
		
    def readHDF5(self,fileName):
        filen=fileName.strip()
        hfile=h5.File(filen,'r')
 
        data=hfile['Phase Data']['data'].value
        freqs=hfile['Phase Data']['data'].attrs['frequencies']
        freqch=hfile['Phase Data']['data'].attrs['frequency channel']
        duration=hfile['Phase Data']['data'].attrs['duration']
        pdtime=hfile['Phase Data']['data'].attrs['time']


        pdate=pdtime[:pdtime.index(" ")]
        ptime=pdtime[pdtime.index(" "):]

        phasedata={'date': pdate,'time':ptime, 'duration':duration,'freqency channel':freqch, 'frequencies':freqs,'data':data}

        return  phasedata
        
        
    
if __name__ == "__main__":

    data = np.random.random(100)
    freqs=np.arange(4.,5.,0.1)
    duration=2.5
    freqChan=1
    filename="testph"

	#write as hdf5 file
    wp=writePhaseData(filename,"hdf5",freqChan,freqs,duration,data)
    wp.Write()

	#write as ascii file
    wp=writePhaseData(filename,"ascii",freqChan,freqs,duration,data)
    wp.Write()

	# read files: 
    a=ReadPhaseData()
   
    # from  ascii file
    x=a.readFile('testph.dat')
    print '\n read ascii file:'
    print x
    # from hdf5 file 
    y=a.readFile('testph.h5')
    print '\n read hdf5 file: '
    print y



	
