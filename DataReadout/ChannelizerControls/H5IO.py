import tables
import numpy as np
import glob, os

class IQData(tables.IsDescription):
    I = tables.Int32Col()
    Q = tables.Int32Col()

class H5Writer():
    def __init__(self):
        self.fileNamePrefix = None
        self.file = None
        self.fileOpened = False
        self.fileName = None
        self.nWrittenToFile = 0

    def __openNextFile(self):
        self.fileName = self.__getNextFileName()
        self.file = tables.open_file(self.fileName, mode='w')
        self.arrays = {}

        self.arrays['I'] = self.file.create_vlarray(self.file.root, 'I',tables.Int32Atom(shape=()),'I',
                                           filters=tables.Filters(1))
        self.arrays['Q'] = self.file.create_vlarray(self.file.root, 'Q',tables.Int32Atom(shape=()),'Q',
                                           filters=tables.Filters(1))
        
        self.fileOpened = True
        self.nWrittenToFile = 0

    def __getNextFileName(self):
        # files are fileNamePrefix followed by %04d.hf:  example data-0012.h5
        print "begin __getNextFileName:  self.fileNamePrefix =",self.fileNamePrefix
        l = glob.glob(self.fileNamePrefix+"*.h5")
        l.sort()
        if len(l) == 0:
            iFile = 0
        else:
            # l is sorted.  Take the last one.  Get the %04d string.  Int it and add one
            iFile = int(os.path.splitext(l[-1])[0].split("-")[1]) +1
        print "===> in getNextFileName:  iFile, l",iFile, l
        return "%s-%04d.h5"%(self.fileNamePrefix, iFile)

    def write(self, iqData, fileNamePrefix):
        if self.fileNamePrefix != fileNamePrefix:
            self.close()
            self.fileNamePrefix = fileNamePrefix
            self.__openNextFile()
        if not self.fileOpened:
            self.__openNextFile()
        for key in self.arrays.keys():
            print "in write:  look for key = ",key
            if key in iqData:
                print "in write:  now write key =",key
                self.arrays[key].append(np.array(iqData[key]).flatten())
        self.nWrittenToFile += 1
        return {"fileName":self.fileName,"nWrittenToFile":self.nWrittenToFile, "fileOpened":self.fileOpened}

    def close(self):
        print "H5Writer: close the file"
        if self.file != None:
            self.file.close()
        self.fileOpened = False
        return {"fileName":self.fileName,"nWrittenToFile":self.nWrittenToFile, "fileOpened":self.fileOpened}


class H5Reader():
    def __init__(self, fileName):
        self.file = tables.open_file(fileName, "r")
        self.iNode = self.file.get_node("/I")
        self.qNode = self.file.get_node("/Q")
        self.nEvent = len(self.iNode)
    def get(self, iEvent, nFreq):
        i = self.iNode[iEvent]
        q = self.qNode[iEvent]        
        return {"I":i, "Q":q}
    def close(self):
        self.file.close()

if __name__ == "__main__":
    filePres = ["junkA","junkB"]
    h5w = H5Writer()
    for i in range(3):
        for filePre in filePres:
            a = {
                "I":[10,20,30],
                "Q":[11,21,31]
                } 
            print h5w.write(a,filePre)
            if filePre == filePres[0]:
                h5w.close()
            b = {
                "I":[10,20,30,40],
                "Q":[11,21,31,41]
                } 
            print h5w.write(b,filePre)
        print h5w.close()

    for filePre in filePres:
        l = glob.glob(filePre+"-*.h5")
        l.sort()
        for fileName in l:
            print "Begin fileName =",fileName
            h5r = tables.open_file(fileName,"r")
            iNode = h5r.get_node("/I")
            qNode = h5r.get_node("/Q")
            for i,q in zip(iNode,qNode):
                print "i =",i
                print "q =",q
                print "=================="
            h5r.close()
