#!/usr/bin/python
try:
    import os,sys,time
    import glob
    import subprocess as sp
    import argparse
    import re
    import threading
    import glob
    import pdb
    import socket
    from timeit import default_timer as timer
    from logModule import Logs
except ImportError:
    raise ImportError("\n -E- Encountered import python exception!!!")


class ClientServer(object):
    """Class to setup Client server connection, send and receive messages
    """
    def __init__(self,link):
        self.link = link.split(',')
        #Create logger instance to save the logs
        self.lobj = Logs("client_logs.txt")
        #Create socket
        self.cobj = ""
        #Server Side download status check
        self.download_status_flag = 1
        #Download (File recv) speed over the network
        self.nw_speed = 0

    def setup_client(self):
        """Function to setup client 
        """
        try:
            self.lobj.logger.info("Creating a Socket connection")
            self.cobj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except Exception as e:
            self.lobj.logger(e)
            self.lobj.logger.error("Fail to create a socket")
            raise e
        
        #Server Local IP
        #self.server_ip = '192.168.0.101'
        #Server Public IP
        self.server_ip = '73.90.155.22'
        #Connect to server on this port
        self.port = 1947 
        try:
            self.lobj.logger.info("Connecting to server {} on port {}".format(self.server_ip,self.port))
            self.cobj.connect((self.server_ip,self.port))
            self.lobj.logger.info("Connection established")            
        except Exception as e:
            self.lobj.logger.error(e)
            self.lobj.logger.error("Failed to connect to server")
            raise e

    def send_data(self):
        """Function to send data to server
        """
        '''
        self.lobj.logger.info("Receiving below handshake signal from server {}".format(socket.gethostname()))
        try:
            self.lobj.logger.info("{}".format(self.cobj.recv(1024)))
            #self.lobj.logger.info("Data received successfully.")
        except Exception as e:
            self.lobj.logger.error(e)
            self.lobj.logger.error("Could not recv data from server")
            raise e
        '''
        self.lobj.logger.info("Sending below youtube-link(s) to server")
        try:
            for link in self.link:
                self.lobj.logger.info(link)
                #self.cobj.send(link)
                self.cobj.sendall(link)
        except Exception as e:
            self.lobj.logger.error(e)
            self.lobj.logger.error("Failure to send the data")

        self.cobj.shutdown(socket.SHUT_WR)

    def check_status(self):
        """Function to check the server status every 5 sec
        """
        #time.sleep(5)
        self.lobj.logger.info("Receiving Download Status from Server {}".format(socket.gethostname()))
        while self.download_status_flag:
            self.lobj.logger.info("Downloading is in progress")
            time.sleep(5)

    def recv_file(self,filename,size):
        self.lobj.logger.info("Receiving dowloaded mp3 from server..")
        with open(filename,'w') as fh:
            #while True:
            #t1 = time.time()
            t1 = timer()
            while int(size) >= len(filename):
                try:
                    data = self.cobj.recv(1024)
                    fh.write(data)
                    if not data:
                        break
                except Exception as e:
                    self.lobj.logger.error("Failed to recv data from server")
            #t2 = time.time()
            t2 = timer()
        self.lobj.logger.info("Finished Receiving")
        self.nw_speed = (float(size)/(1024*1024)) / (t2 - t1)
        

    def recv_data(self):
        """Function to receive the data (downloaded youtube file) from server
        For each link server will send mp3 and mp4 file
        1. Based on total no of links twice no of files will be created
        """
        length_of_file = self.cobj.recv(1024)
        self.download_status_flag=0 #Reset download_status flag indicating server is ready to transfert the file
        time.sleep(1)
        name_of_file = self.cobj.recv(1024)
        self.lobj.logger.info("Receiving File From Server :: Name -> {} Size -> {} bytes".format(name_of_file,length_of_file))
        time.sleep(1)
        self.recv_file(name_of_file,length_of_file)
         

    def runTest(self):
        #Define steps here
        self.setup_client()
        self.send_data()
        t1 = threading.Thread(target=self.check_status)
        t2 = threading.Thread(target=self.recv_data)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        time.sleep(1)
        self.lobj.logger.info("Network Speed is {} mb/sec".format(self.nw_speed))
        self.lobj.logger.info("Thank-you for downloading....Exit")
        #self.recv_data()
        #Just wait
        

def getArgs():
    """Function to get command line arguments
    """
    parser = argparse.ArgumentParser(description='Script to send youtube links to server which will download the files and will send  back to client', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-l','--link',dest='link',help='Single or multiple links separated by csv or a file containing youtube links per line',required=True)
    args = parser.parse_args()
    return args.link


if __name__ == '__main__':
    link = getArgs()
    obj = ClientServer(link)
    obj.runTest()

