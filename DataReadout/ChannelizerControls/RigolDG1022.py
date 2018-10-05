"""
Tested with only the RIGOL DG1022 on the USB.  Need some logic if other USB
devices are plugged in.

Commands described in doc/DG1022_ProgrammingGuide_EN.pdf

Keep it simple, so only control Channel 1.

You need to do this once on the system:
$ sudo cp 97-RigolUSBTMC.rules /etc/udev/rules.d/

Yeed to do this each time after plugging in the RIGOL DG1022
$ sudo chmod a+rw /dev/usbtmc0

Chris S.  September 2018
"""

# This module is from https://github.com/pklaus/universal_usbtmc
import universal_usbtmc

class RigolDG1022():
    """Control the RIGOL DG1022 Function Generator"""

    def __init__(self):
        """ Connect and make sure the device is there"""
        backend = universal_usbtmc.import_backend("linux_kernel")
        try:
            self.be = backend.Instrument("/dev/usbtmc0")
        except universal_usbtmc.exceptions.UsbtmcNoSuchFileError:
            raise Exception("RigolDG1022 USB is not connected")
        except universal_usbtmc.exceptions.UsbtmcPermissionError:
            raise Exception("RigolDG1022: run this:  sudo chmod a+rw /dev/usbtmc0")
        except OSError:
            raise Exception("RigolDG1022: run this:  cp 97-RigolUSBTMC.rules /etc/udev/rules.d/")

        response = self.be.query("*IDN?")
        name = "RIGOL TECHNOLOGIES,DG1022"
        if not response.startswith(name):
            raise Exception("USB device is not %s"%name)

    def enableOutput(self):
        """Actually generate whatever voltage has been specified"""
        self.be.write("OUTP ON")
        
    def disableOutput(self):
        """Do not generate output voltage"""
        self.be.write("OUTP OFF")
        
    def setDCLevel(self, dcLevel):
        """
        Set the DC level
        """
        command = "APPL:DC DEV,DEV,%f"%dcLevel
        self.be.write(command)
        readbackValue = self.getDCLevel()
        if dcLevel != readbackValue:
            raise ValueError("dcLevel=%f but readbackValue=%f"%(dcLevel, readbackValue))

    def sendQuery(self, query):
        """Try the query three times, catching time outs"""
        rv = None
        for i in range(3):
            try:
                rv = self.be.query(query)
                break
            except OSError:
                if i == 2:
                    raise Exception("query timed out three times")
        return rv
    
    def getDCLevel(self):
        """ 
        Return the DC level in volts, or throw an exception if it is not
        generating a DC level
        """
        # rv will be a line like this:
        # u'CH1:"ARB,1.234000e+03,5.000000e-01,-1.500000e+00"\n'
        rv = self.sendQuery("APPL?")
        rvl = rv.split(":")
        vals = rvl[1][1:-2].split(',')
        if vals[0] == 'ARB':
            retval = float(vals[3])
            return retval
        raise ValueError("ARB is not being generated")

    def getOutput(self):
        """
        Return True if output is enabled, False if output is not enables
        """
        rv = self.be.query("OUTPUT?")
        return rv.startswith("ON")
    
if __name__ == "__main__":
    rigol = RigolDG1022()
    
        
    
