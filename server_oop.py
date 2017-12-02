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
    from logModule import Logs
    from youtubeClass import Youtubedl
except ImportError:
    raise ImportError("\n -E- Encountered import python exception!!!")

class ServerConnect(object):
    """Class to setup initial settings of server
    """
    def __init__(self):

        #Create a logger object
        self.obj = Logs("server_logs.txt")  
        #Create a socket object
        self.so_obj = ''
        #Client_socket object
        self.cs = ''
        #Yotubedl Object instance
        self.yt = ''
        #Set Buffer Size
        self.buffer_size = 1024
        #List of youtube links recieved from client
        self.client_youtube_links = []
        #Download status flag
        self.download_flag = 1

    def setup_server(self):
        """Function to create socket, bind, listen
        """
        try:
            self.obj.logger.info("Creating a Socket object")
            self.so_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except Exception as e:
            self.obj.logger.error(e)
            self.obj.logger.error("Failed to create a socket")
            raise e

        #Server IP
        self.server_ip = '192.168.0.101'
        #Reserve a port
        self.server_port = 1947
        #Bind to server IP and port
        self.obj.logger.info("Binding to host {} and port {}".format(self.server_ip,self.server_port))
        #self.so_obj.bind(('',self.server_port)) # Empty IP : This makes server to listen to the request coming from other clients on the same network.
        #self.so_obj.bind(('{}'.format((self.server_ip,self.server_port)))
        self.so_obj.bind((self.server_ip,self.server_port))
        #Put socket into listening mode
        self.obj.logger.info("Socket is listening")
        self.so_obj.listen(5)   # Tells the socket library that we want it to queue up as many as 5 connect requests (the normal max) before refusing outside connections

    def receive_data(self):
        """Function to send and receive data to/from client
        """
        '''
        self.obj.logger.info("Sending handshake to Client")
        try:
            self.cs.send("Hello Client, thank you for connecting\n")
        except Exception as e:
            self.obj.logger.error(e)
            self.obj.logger.error("Failed to send data to client")
            raise e
        '''
        self.obj.logger.info("Now receiving data from Client")
        self.client_data = self.cs.recv(self.buffer_size)
        self.client_youtube_links = self.client_data.split(',')
        while True:
             self.client_data = self.cs.recv(self.buffer_size)
             if self.client_data:
                self.obj.logger.info("More data coming")
             else:
                self.obj.logger.info("No more data")
                break
        self.obj.logger.info("List of Youtube Links received from client: {} ".format(self.client_youtube_links))


    def send_data(self):
        """Function to send dowloaded files to client. For each link mp3 and mp4 file will be sent
        """
        #Getting mp3 files
        #self.cs.send("Save data in file dont print.")
        #return
        try:
            mp3_files = glob.glob("/home/neo/public_html/myDrive/youtube_downloads/audio/*mp3")
            self.obj.logger.info("Total no of mp3 files to be sent : {}".format(len(mp3_files)))
            self.cs.send(str(len(mp3_files)))
            for mp3 in mp3_files:
                #Send file-size and name of audio file
                self.obj.logger.info("Send file size of "+mp3)
                file_size = os.path.getsize(mp3)
                self.cs.send(str(file_size))
                time.sleep(1)
                basename = os.path.basename(mp3)
                mp3_name = ''.join(e for e in basename[:-4] if e.isalnum())+'.mp3'
                self.obj.logger.info("Send file name "+mp3_name)
                self.cs.send(str(mp3_name))
                time.sleep(1)
                self.obj.logger.info("Sending {} data to client".format(mp3_name))
                fh = open(mp3,'rb')
                data = fh.read(1024)
                while data:
                    self.cs.send(data)
                    data = fh.read(1024)
                fh.close()
                self.obj.logger.info("Sending {} to client complete.".format(mp3_name))
                time.sleep(2)
        except Exception as e:
            self.obj.logger.error(e)
            self.obj.logger.error("Failed to send the data to client")


    def process_client_youtube_link(self):
        """Function to download youtube links
        Use thread here. One to download youtube videos and one to send the status of download to client
        """
        #time.sleep(10)
        #return
        for link in self.client_youtube_links:
            self.yt = Youtubedl(link)
            status = self.yt.runYoutube()
        #Reset youtube_links_list
        self.client_youtube_links = []
        #Set the flag once download is complete
        #self.download_flag = 0
        time.sleep(5)

    def send_download_status(self):
        """Function to send download status to client every 5 sec
        """
        while self.download_flag:
            time.sleep(5)
            self.obj.logger.debug("Download is in progress")
        #Reset flag to 1
        self.download_flag = 1
    
    def run_server(self):
        """Server will be running in a forever loop unless there is an error or manual interrupt
        """
        while True:
            try:
                self.obj.logger.info("Initiating a connection with Client")
                self.cs, addr = self.so_obj.accept()
                self.obj.logger.info("Got connection from {}".format(addr))
            except Exception as e:
                self.obj.logger.error(e)
                self.obj.logger.error("Failed to connect with Client")
                raise e

            self.receive_data()
            t1 = threading.Thread(target = self.process_client_youtube_link)
            #t2 = threading.Thread(target = self.send_download_status)
            t1.start()
            #t2.start()
            t1.join()
            #t2.join()
            time.sleep(5)
            self.obj.logger.info("Now sending data to client")
            self.send_data()
            self.obj.logger.info("Closing the connection with Client\n")
            self.obj.logger.info("************************************\n")
            self.cs.close()

    def runTest(self):
        #Define steps here
        self.setup_server()
        self.run_server()
    

if __name__ == '__main__':
    obj = ServerConnect()
    obj.runTest()

