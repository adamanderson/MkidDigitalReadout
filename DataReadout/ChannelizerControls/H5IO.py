import tables
import numpy as np

class IQData(tables.IsDescription):
    I = tables.Int32Col()
    Q = tables.Int32Col()

class H5Writer():
    def __init__(self, fileName):
        self.fileName = fileName
        self.file = tables.open_file(fileName, mode='w')
        self.Iarray = self.file.create_vlarray(self.file.root, 'I',tables.Int32Atom(shape=()),'I',
                                           filters=tables.Filters(1))
        self.Qarray = self.file.create_vlarray(self.file.root, 'Q',tables.Int32Atom(shape=()),'Q',
                                           filters=tables.Filters(1))
        self.closed = False

    def write(self, iqData):
        if self.closed:
            raise Exception("Close already called for %s"%self.fileName)
        self.Iarray.append(np.array(iqData['I']))
        self.Qarray.append(np.array(iqData['Q']))
        
    def close(self):
        self.file.close()
        self.closed = True

if __name__ == "__main__":
    h5w = H5Writer("junk.h5")
    a = {
        "I":[10,20,30],
        "Q":[11,21,31]
        } 
    h5w.write(a)
    b = {
        "I":[10,20,30,40],
        "Q":[11,21,31,41]
        } 
    h5w.write(b)
    h5w.close()

    h5r = tables.open_file("junk.h5","r")
