import numpy as np
from scipy.signal import welch
import matplotlib.pyplot as plt

class PlotProcessor():
    def __init__(self, domain="time"):
        self.domain = domain # time or frequency
        self.mode = None
        self.nEma=0
        self.nCma = 0
        
    def reset(self):
        self.nEma=0
        self.nCma = 0
        self.cma=0
        self.ema=0
        self.nfCma = 0
        self.fcma=0
        
        
    def setMode(self,mode):
        self.mode = mode
        if self.mode == "cma": # cumulative moving average
            self.nCma = 0
            self.nfCma = 0
        elif self.mode == "ema":
            self.nEma = 0
            self.ema=0
                 
    def process(self, timeDomainData, alpha=0.1):
        self.alpha=alpha
        retval = {
            "domain":self.domain,
            "mode":self.mode,
            }

        if self.domain == "time":
            x = timeDomainData
            
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
            elif self.mode == "ema":
                if self.nEma == 0:
                    self.ema = timeDomainData
                else:
                    self.ema = self.alpha*timeDomainData+ (1.0-self.alpha)*self.ema
                self.nEma += 1
                retval['values'] = self.ema      
            else:    
                raise ValueError("teach me how to deal with mode =",self.mode)
            return retval
        
        elif self.domain == "freq":
            x =  timeDomainData
            fs = 1e6 
            window = 'hanning'
            nperseg = len(x)
            noverlap = 0
            nfft = None
            detrend = 'constant'
            f,pxx = welch(x,fs,window,nperseg,noverlap,nfft,detrend,scaling='spectrum')
             
            if self.mode is None:
                retval['spectrum'] = pxx
                
            elif self.mode == "cma":
                if self.nfCma == 0:
                    self.fcma = pxx
                else:
                    self.fcma = (pxx+ self.nfCma*self.fcma)/(self.nfCma+1)
                self.nfCma += 1
                retval['spectrum'] = self.fcma
            else:    
                raise ValueError("teach me how to deal with mode =",self.mode)
        else:
            raise ValueError("teach me how to deal with domain =",self.domain)
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


    # Exponential moving average
    pp.setMode("ema")
    alpha=0.1
    ema_s=0
    for i in range(5):
        x = i*np.ones(10)
        y = pp.process(x,alpha)
        v = y['values']
        if i>0 : ema_s = ema_s*(1-alpha)+alpha*i
        assert np.all(ema_s == v)

    # frequency domain
    pf = PlotProcessor("freq")
    pf.reset()
    #default just return the spectrum
    for i in range(5):
        x=np.arange(0,2*np.pi,0.01*np.pi)
        y=np.sin(i*x)
        v = pf.process(y)["spectrum"]

    pf.setMode("cma")
    # return the cumulative average spectrum 
    for i in range(5):
        x=np.arange(0,2*np.pi,0.01*np.pi)
        y=np.sin(i*10*x)
        v = pf.process(y)["spectrum"]
    plt.plot(v)
    plt.show()
 #       print v
        

        

        
