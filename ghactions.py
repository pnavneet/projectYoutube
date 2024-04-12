"""
This file is created only for GH actions learning purpose.
Creating dummy functions, for PR creation and triggering the workflow
"""

class Utils(object):

    def __init__(self):
        self.server_ip = None
        self.server_port = None
        self.client_ip = None
        self._set_server_client_ip_port()
    
    def _set_server_client_ip_port(self):
        """ Internal function to set server ip and client ip"""
        pass

    def get_server_ip(self):
        """ Function which returns server ip"""
        return self.server_ip

    def get_client_ip(self):
        """ Function which returns client ip"""
        return self.client_ip
    
