import numpy as np
class PlotProcessor():
    def __init__(self, domain="time"):
        self.domain = domain # time or frequency
        self.mode = None

    def setMode(self,mode):
        self.mode = mode
        if self.mode == "cma": # cumulative moving average
            self.nCma = 0
        
    def process(self, timeDomainData):
        retval = {
            "domain":self.domain,
            "mode":self.mode,
            }

        if self.domain == "time":
            x = timeDomainData
        else:
            raise ValueError("teach me how to deal with domain =",self.domain)
        
        if self.mode is None:
            retval['values'] = x
        elif self.mode == "cma":
            if self.nCma == 0:
                self.cma = timeDomainData
            else:
                self.cma = (timeDomainData + self.nCma*self.cma)/(self.nCma+1)
            self.nCma += 1
            retval['values'] = self.cma
            retval['nCma'] = self.nCma
        else:
            raise ValueError("teach me how to deal with mode =",self.mode)

        return retval
        
if __name__ == "__main__":
    pp = PlotProcessor()

    # Default:  just return the values
    for i in range(5):
        x = i*np.ones(10)
        v = pp.process(x)['values']
        assert np.all(x==v)

    # Cumulative moving average
    pp.setMode("cma")
    for i in range(5):
        x = i*np.ones(10)
        y = pp.process(x)
        v = y['values']
        assert np.all(0.5*i == v)
        assert y['nCma'] == i+1

    # just return the values
    pp.setMode(None)
    for i in range(5):
        x = i*np.ones(10)
        v = pp.process(x)['values']
        assert np.all(x==v)

    # Cumulative moving average
    pp.setMode("cma")
    for i in range(5):
        x = i*np.ones(10)
        y = pp.process(x)
        v = y['values']
        assert np.all(0.5*i == v)
        assert y['nCma'] == i+1

        

        
