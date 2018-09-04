import h5py as h5 
import numpy as np
import datetime
import os

class WritePhaseData():
    """ 
    Write phase data to a file in either ASCII or HDF5 format.

    called as:
     WritePhase.writePhase(filename,format,freqChan,freqs,duration,phases)

    filename: file name, default "test"
    format:  file format,"ascii" or "hdf5". Phases is written to filename.dat or filename.h5, respectively
    freqChan: channel number of the frequency
    freqs: array of frequencies in use (obtained from freqs=rchc.roachController.freqChannels )
    duration: duration to collect data
    phases: Roach data array  (obtained  from phases = rchc.roachController.takePhaseStreamDataOfFreqChannel(
            freqChan=freqChan, duration=duration, hostIP=hostIP, fabric_port=port) )
    """
    def __init__(self,fileName,fFormat,freqChan,frequencies,duration,phases):
        self.fileName = fileName
        self.freqChan = freqChan
        self.duration=duration
        self.fFormat=fFormat.strip()
        self.phases = phases
        self.freqs = frequencies
        print "WritePhaseData format=",format," phases[:4]=",phases[:4]
        self.write()
        if not (self.fFormat is "ascii" or self.fFormat is "hdf5"):
            raise ValueError("fFormat must be ascii or hdf5, not %s"%fFormat)
    
    def writeAscii(self):
        dtime=str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")) 
        print dtime
        sdtime="Time : "+dtime +"\n" 
        sdur = "Duration : %6.3fs\n"%self.duration
        schan= "Frequency Channel: %d \n"%self.freqChan	
        filename=self.fileName+".dat"	
        nfile = open(filename,'wb')  
        nfile.write(sdtime)
        nfile.write(sdur)
        nfile.write(schan)
        nfile.write("Frequencies: \n")
        np.savetxt(nfile, self.freqs)
        nfile.write("phases \n")	     
        np.savetxt(nfile, self.phases)


    def writeHDF5(self):
        dtime=str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")) 

        filename=self.fileName+".h5"
        if os.path.exists(filename):
  	    fileh=h5.File(filename,"w")  
        else:
            fileh=h5.File(filename,"w")

        grp = fileh.create_group('/Phase Data')
        grp['phases']=self.phases
        dset=grp['phases']
        dset.attrs['time']=dtime
        dset.attrs['duration']=self.duration
        dset.attrs['frequency channel']=self.freqChan
        dset.attrs['frequencies']=self.freqs
        print "In WritePhaseData:  phases[:4]=",self.phases[:4]
        fileh.flush()
        fileh.close()


    def write(self):
        if self.fFormat is "ascii":
            self.writeAscii()
        elif self.fFormat is "hdf5":
            self.writeHDF5()		


class ReadPhaseData():
    """
    Read back phase data, given a file name

    Returns:  dictionary of "frequencies", "duration", "frequency channel", and "phases"
    """
    def __init__(self, fileName):
        type = os.path.splitext(fileName)[1][1:]
        if type=="dat":
	         x=self.readAscii(fileName)
           
        elif type=="h5":
            x=self.readHDF5(fileName)
            
        else:
            raise ValueError("extension must be dat or h5, not %s"%type)

        self.data = x


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

        dindex=lines.index("phases \n")
        freqlist=lines[4:dindex]
        freqs=np.float_(freqlist)	

        datalist=lines[dindex+1:]
        phases=np.float_(datalist)

        phasedata={'date': pdate,'time':ptime, 'duration':duration,'frequency channel':freqch, 'frequencies':freqs,'phases':phases}
		
        return  phasedata
		
    def readHDF5(self,fileName):
        filen=fileName.strip()
        hfile=h5.File(filen,'r')
 
        phases=hfile['Phase Data']['phases'].value
        freqs=hfile['Phase Data']['phases'].attrs['frequencies']
        freqch=hfile['Phase Data']['phases'].attrs['frequency channel']
        duration=hfile['Phase Data']['phases'].attrs['duration']
        pdtime=hfile['Phase Data']['phases'].attrs['time']


        pdate=pdtime[:pdtime.index(" ")]
        ptime=pdtime[pdtime.index(" "):]

        phasedata={'date': pdate,'time':ptime, 'duration':duration,'frequency channel':freqch, 'frequencies':freqs,'phases':phases}

        return  phasedata
        
        
    
if __name__ == "__main__":

    phases = np.random.random(100)
    freqs=np.arange(4.,5.,0.1)
    duration=2.5
    freqChan=1
    original = {
        "frequencies":freqs,
        "duration":duration,
        "frequency channel":freqChan,
        "phases":phases
        }
    filename="testph"
    
    #write as hdf5 file
    wp=WritePhaseData(filename,"hdf5",freqChan,freqs,duration,phases)

    #write as ascii file
    wp=WritePhaseData(filename,"ascii",freqChan,freqs,duration,phases)

    # read files: 
    # from  ascii file
    x=ReadPhaseData('testph.dat').data
    print '\n read ascii file:'
    allGood = True
    for k in original:
        if not np.all(original[k]==x[k]):
            print "trouble reading back",k,"from ascii file"
            allGood = False
    if allGood: print "success reading back ascii file"

    # from hdf5 file 
    x=ReadPhaseData('testph.h5').data
    print '\n read hdf5 file: '
    allGood = True
    for k in original:
        if not np.all(original[k]==x[k]):
            print "trouble reading back",k,"from hdf5 file"
            allGood = False
    if allGood: print "success reading back hdf5 file"



	
