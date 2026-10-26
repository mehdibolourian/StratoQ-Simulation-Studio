"""Only the property container used by upstream analytical channel classes.

NetSquid is still required for event-based channel_simulation. The original
analytical UplinkChannel/DownlinkChannel math does not depend on its simulator;
this minimal parent permits those upstream numerical methods to run unchanged.
"""
import numpy as np

class QuantumErrorModel:
    def __init__(self, *args, **kwargs):
        self.properties = {}

    def lose_qubit(self, *args, **kwargs):
        raise RuntimeError('Event-based quantum simulation requires licensed NetSquid.')

class simtools:
    @staticmethod
    def get_random_state():
        return np.random.RandomState()

def warn_deprecated(*args, **kwargs):
    import warnings
    warnings.warn(str(args[0]), DeprecationWarning, stacklevel=2)
