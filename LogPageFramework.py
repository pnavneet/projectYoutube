'''
********************************************************************************
@file       :       LogPageFramework.py
@brief      :       To create a dynamic and scalable framework that will communicate with NVMe Spec and vendor specific log pages
					https://confluence.wdc.com/display/DVV/FVT+Log+Page+Framework
@spec       :       NVM Express Base Specification, Hyperscale NVMe Boot SSD Specification
@author     :       Khoa Phan
@date       :       7/5/2022
@copyright (C) 2022 SanDisk a Western Digital brand
********************************************************************************
'''


import GlobalVars
import Core.ValidationError as ValidationError
import Core.ProtocolFactory as ProtocolFactory
import Constants
import json, os
from collections import OrderedDict


class LogPageFramework(object):
	def __init__(self, vtfContainer=None):
		"""
		@brief The constructor and initialization method for class LogPageFramework
		       LogPageFramework contains LogPageObject class, finder methods for log page JSON files, and parsing methods between LogPageObject, JSON, and NVMe log buffer
		       A new instance is made for each LogPageObject (which is one individual log page)
		"""
		# when deviceReport=False and vtfContainer is not provided.
		if not hasattr(self, 'vtfContainer') and not vtfContainer:
			self.vtfContainer = ProtocolFactory.ProtocolFactory.createVTFContainer("NVMe")
		elif vtfContainer:
			self.vtfContainer     = vtfContainer
		self.globalVarsObj	= GlobalVars.GlobalVars(self.vtfContainer)
		self.printUtilsObj 	= self.globalVarsObj.printUtils
		self.ccmObj		= self.globalVarsObj.ccmObj
		self.utilsObj		= self.globalVarsObj.utilObj
		self.buffer_parsed = None
		self.vendor_name = None

		#Add relevant functions for respective log page id
		self.findCorrectJSONFileDict = {
		    'Generic': self.__findLogPageJSONFileGeneric,
		    'Dell': self.__findLogPageJSONFileVendor_Dell,
		    'CalX': self.__findLogPageJSONFileVendor_CalX
		}


	class LogPageObject(object):
		def __init__(self, hex_id, log_page_name, version, vendor, length, defaultPersistence, attributes):
			"""
			@brief The initialization method for class LogPageObject. This contains all attributes and sub-attributes for a log page.
			@param hex_id The hexadecimal ID of the log page. Obtained from Constants module in ValidationLib (example: "0xc0")
			       log_page_name The name of the log page. Obtained from Constants module in ValidationLib (example: "SMART_PAGE_ID_MSFT_C0")
			       version The version of the spec the current LogPageObject instance is based on (example: "2.0", "1.4-2.0", "A05", "A05-A06")
			       vendor The vendor current LogPageObject instance is for. 'Generic' if not for any vendor (example: "Microsoft", "Generic")
			       length The amount of bytes current LogPageObject instance has (example: 512)
				   defaultPersistence The default persistency behavior of attributes across different scenarios
			       attributes An OrderedDict containing all attributes of current LogPageObject instance. Used to access, obtain, and store values from the NVMe buffer.
			                  The key of each item in attributes OrderedDict is the name of an attribute (example: "CriticalWarning")
			                  The value of each item is an OrderedDict with the sub-attributes of the key attribute
			                        byte_offset The index of the attribute's first byte in the NVMe buffer
			                        num_of_bytes The byte length of the attribute in the buffer
			                        default_value The default value of the attribute in this instance (None by default). Used to compare with current_value below for tests
			                        persistency Whether certain processes (example: power cycles) will, might, or will not affect the current attribute
			@note Log values parsed from the buffer later will be parsed as CLASS ATTRIBUTES of the LogPageObject, NOT in 'attributes'
			      (example: LogPageObject.CriticalWarning, LogPageObject.UnsafeShutdowns)
			      Buffer values are parsed this way due to the nature of the existing tests: where values are called with the 'getattr' method
			      directly on the log object. Storing the buffer values inside 'attributes' OrderedDict will prevent these tests from obtaining these log values.
			"""
			self.hex_id = hex_id
			self.log_page_name = log_page_name
			self.version = version
			self.vendor = vendor
			self.length = length
			self.defaultPersistenceOfAttributes = defaultPersistence
			self.attributes = attributes
			for attr in self.attributes:
				self.attributes[attr]['default_value'] = None

		def getHexID(self):
			"""
			@return The hexadecimal ID of the LogPageObject instance
			@example '0x2'
			"""
			return self.hex_id

		def getLogPageName(self):
			"""
			@return The log page name of the LogPageObject instance
			@example 'SMART_PAGE_ID_GENERIC'
			"""
			return self.log_page_name

		def getVersion(self):
			"""
			@return The version of the NVMe Specification this LogPageObject instance is based on
			@example "2.0", "1.4-2.0", "A05", "A06"
			"""
			return self.version

		def getVendor(self):
			"""
			@return The vendor of the LogPageObject instance
			@example 'Generic', 'Dell', 'Xbox'
			"""
			return self.vendor

		def getLength(self):
			"""
			@return The byte length (as Integer type) of all the Attributes inside the LogPageObject instance
			@example 512
			"""
			return self.length

		def getAllAttribute(self):
			"""
			@return The OrderedDict containing all log page attributes and each of their sub-attributes
			"""
			return self.attributes

		def getSpecificAttribute(self, attr):
			"""
			@return The OrderedDict containing only sub-attributes of attr
			"""
			return self.attributes[attr]

		def getAttributeByteOffset(self, attr):
			"""
			@return The byte offset of attr in NVMe buffer
			"""
			return self.attributes[attr]['byte_offset']

		def getAttributeByteLength(self, attr):
			"""
			@return The byte length of attr in NVMe buffer
			"""
			return self.attributes[attr]['num_of_bytes']

		def getAttributeDefaultValue(self, attr):
			"""
			@return The default value of attr
			"""
			return self.attributes[attr]['default_value']

		def setAttributeDefaultValue(self, attr, new_default_value):
			"""
			@brief Change the default value of attr
			"""
			self.attributes[attr]['default_value'] = new_default_value

		def getAttributeCurrentValue(self, attr):
			"""
			@return The current value of attr
			@note Only called after parsed from buffer
			"""
			return getattr(self, attr)

		def getAllAttributeCurrentValues(self):
			"""
			@brief Obtain only LogPageObject class attributes that exist as keys in attributes OrderedDict
			@return An OrderedDict containing all current_value of LogPageObject
			"""
			all_current_dict = {}
			for attr in self.attributes:
				all_current_dict[attr] = self.getAttributeCurrentValue(attr)
			return all_current_dict

		def setAttributeCurrentValue(self, attr, new_current_value):
			"""
			@brief Change the current value of attr
			@note Only called after parsed from buffer
			"""
			setattr(self, attr, new_current_value)

		def getAttributePersistency(self, attr):
			"""
			@return The persistency List of attr
			"""
			return self.attributes[attr]['persistency']

		def compareAttributeDefaultVersusCurrent(self, attr):
			"""
			@brief Compare the default and current of attr for tests
			@return True if default_value is not None, and default and current match
			        False if default is None, or default and current don't match
			"""
			if hasattr(self, attr) == False:
				raise ValidationError.TestFailError("LogPageObject.compareAttributeDefaultVersusCurrent()",
				                                    "the attr either does not exist or is not passed as class attribute into this LogPageObject")
			if self.attributes[attr]['default_value'] != None:
				return True if self.attributes[attr]['default_value'] == self.attr else False
			else:
				raise ValidationError.TestFailError("LogPageObject.compareAttributeDefaultVersusCurrent()",
				                                    "default_value of this attribute is currently None")

		def getJSONFileName(self):
			"""
			@return The conventionally correct name for the JSON file of the LogPageObject
			"""
			return str(self.hex_id + '_v' + self.version + '.json')
		
		def getDefaultAttributesPersistence(self):
			"""
			@return Dictionary containing the default persistency behavior of attribute across different scenarios
			"""
			return self.defaultPersistenceOfAttributes


	def __findVendorName(self, hex_id):
		"""
		@brief Return the correctly formatted vendor name, or "Generic"
		@param hex_id The hexadecimal ID of the needed log page
		@return "Generic", or vendor name in title case (ex: "Dell","calx2microsofteng")
		"""
		is_generic = True if hex_id < 92 else False
		self.vendor_name = "Generic" if is_generic else self.utilsObj.GetDeviceVendorName().title()
		if "Calx" in self.vendor_name: #calx2microsofteng, calx3microsofteng
			self.vendor_name = "CalX"
		return self.vendor_name



	def __linkWithSpecificFolder(self, hex_id, files_filtered=False):
		"""
		@brief Return the precise folder path to obtain the JSON Log Page
		@param hex_id The hexadecimal ID of the needed log page
		@return: files_filtered = False : The precise folder path to find the JSON file (as String) 
				 files_filtered = True  : The precise folder path to find the JSON file and list of files with matching log page id
		"""
		json_folder_path = r'{}'.format(Constants.LOGPAGE_JSON_FOLDER)
		self.__findVendorName(hex_id) #update vendor name
		if self.vendor_name == "Generic":
			json_folder_path = r"{}\Generic".format(json_folder_path)
		else:
			json_folder_path = r"{}\Vendor\{}".format(json_folder_path, self.vendor_name)
		if files_filtered:
			matched_flies = []
			for _folder, _subfolders, files in os.walk(json_folder_path):
				for file in files:
					if file.endswith(".json"):
						underscore = file.index('_')
						file_hex_id = file[0:underscore]
						file_hex_id = int(file_hex_id, 16)
						if file_hex_id == hex_id: #match current file hex with wanted hex	
							matched_flies.append(file)
			return matched_flies, underscore
		else:
			return json_folder_path

	def __findLogPageJSONFileGeneric(self, needed_hex_id):
		"""
		@brief Traverse 'LogPageJSON/Generic' to find the correct JSON file
		@param needed_hex_id The hex_id of the Generic log page
		@return The name of the JSON file being found (ex: '0x2_v1.4-2.0.json')
		"""
		needed_version = self.utilsObj.GetNVMeVersion()
		json_files, underscore = self.__linkWithSpecificFolder(needed_hex_id, files_filtered=True)
		for file in json_files:
			json_suffix = file.index('.json')
			file_version = file[underscore+2:json_suffix] #extract only the A.B-C.D or A.B portion of file
			if '-' in file_version: #A.B-C.D version format (version range from first to last for 1 JSON)
				file_version_split = file_version.split('-')
				file_version_first = float(file_version_split[0])
				file_version_last = float(file_version_split[1])
				if needed_version >= file_version_first and needed_version <= file_version_last:
					return file
			else: #A.B version format (1 version for 1 JSON, not a range of versions)
				if file_version == needed_version:
					return file
		raise ValidationError.TestFailError("LogPageFramework.__findLogPageJSONFileGeneric()",
		                                    "JSON File cannot be found. Ensure either the file exists, and arguments are correct.")

	def __findLogPageJSONFileVendor(self, needed_hex_id, needed_version):
		"""
		@brief Traverse 'LogPageJSON/Vendor/' to find the correct JSON file
		@param needed_hex_id - log page id
		@return The name of the JSON file being found (ex: '0xca_vA06.json')
		"""
		json_files, underscore = self.__linkWithSpecificFolder(needed_hex_id, files_filtered = True)
		for file in json_files:		
			json_suffix = file.index('.json')
			file_version = file[underscore+2:json_suffix] #extract only the Ay-Az or Ay portion of file
			if '-' in file_version: #A.B-C.D version format (version range from first to last for 1 JSON)
				file_version_split = file_version.split('-') #for Ay-Az, split to ['Ay','Az']
				file_version_first = int(file_version_split[0][1:]) #index [1:] to remove the "A"
				file_version_last = int(file_version_split[1][1:])
				needed_version_check = int(needed_version[1:])
				if needed_version_check >= file_version_first and needed_version_check <= file_version_last:
					return file
				else: #Ay version format (1 version for 1 JSON, not a range of versions)
					if file_version == needed_version: #version matches exactly
						return file
		raise ValidationError.TestFailError("LogPageFramework.__findLogPageJSONFileVendor()",
		                                    "JSON File cannot be found. Ensure either the file exists, and arguments are correct.")

	def __findLogPageJSONFileVendor_CalX(self, needed_hex_id):
		"""
		@brief: Calls findLogPageJsonFileVendor with logPageHexId and required logPageVersion
		@input : hex_id (example: '0xd0')
		@returns : corresponding log page json file (ex: '0xd0_v1.json')
		"""
		version_number = self.buffer_parsed.GetTwoBytesToInt(510) 
		vendor_name = self.utilsObj.GetDeviceVendorName().title() 
		needed_version = (vendor_name + "-v" + str(version_number))

		json_files, underscore = self.__linkWithSpecificFolder(needed_hex_id, files_filtered = True)

		for file in json_files:
			json_suffix = file.index('.json')
			file_version = file[underscore+1:json_suffix] #compare json file name
			if file_version == needed_version: return file

		raise ValidationError.TestFailError("LogPageFramework.__findLogPageJSONFileVendor()",
		                                    "JSON File cannot be found. Ensure either the file exists, and arguments are correct.")

	def __findLogPageJSONFileVendor_Dell(self, needed_hex_id):
		"""
		@brief: Calls findLogPageJsonFileVendor with logPageHexId and logPageVersion
		@input : hex_id (example: '0xca')
		@returns : corresponding log page json file (ex: '0xca_vA06.json')
		"""			
		needed_version = self.globalVarsObj.GenericFWStructure.Morpheous_map['GLP']['DellSpecVersion']
		return self.__findLogPageJSONFileVendor(needed_hex_id, needed_version)

	def __readLogPageObjectFromJSON(self, hex_id):
		"""
		@brief Parse a LogPageObject from a log page JSON file
		@param hex_id The hex_id of the needed log page (example: '0x2', 0xca')
		@return LogPageObject with values from JSON file
		@note This LogPageObject does not contain current_value yet, current_value only exists after parsing from buffer.
		"""
		json_folder_path = self.__linkWithSpecificFolder(hex_id)
		json_file_name = self.findCorrectJSONFileDict[self.vendor_name](hex_id)
		with open(str(json_folder_path + '\\' + json_file_name), 'r') as file_read:
			log_page_ordered_dict = json.load(file_read, object_pairs_hook=OrderedDict)
		file_read.close()
		hex_id = log_page_ordered_dict['hex_id']
		log_page_name = log_page_ordered_dict['log_page_name']
		version = log_page_ordered_dict['version']
		vendor = log_page_ordered_dict['vendor']
		length = log_page_ordered_dict['length']
		defaultPersistence = log_page_ordered_dict['defaultPersistence']
		attributes = log_page_ordered_dict['attributes']
		log_page_object = self.LogPageObject(hex_id, log_page_name, version, vendor, length, defaultPersistence, attributes)
		return log_page_object

	def readLogPageObjectFromBuffer(self, hex_id, RAE=1, return_dict=False, checkbuffersize = False):
		"""
		@brief NVMe buffer contains values that represent the state of the drive being tested
		       Here, a LogPageObject is generated to contain those values
		       This is the "main method" of LogPageFramework
		@param log_hex_id Hexadecimal ID of the needed log page file (example: '0xca', '0x2')
		       RAE Retain Async Event, refer to NVMe spec section 5.2
		       return_dict If False, return LogPageObject. If True, return __dict__ of LogPageObject
		@return LogPageObject (or LogPageObject.__dict__) with values parsed from buffer, passed as a class attribute of the LogPageObject
		"""
		self.buffer_parsed = self.ccmObj.GetLogPageNVMe(pageID=hex_id, RAE=RAE)
		log_page_object = self.__readLogPageObjectFromJSON(hex_id)
		all_attribute = log_page_object.getAllAttribute()
		
		if checkbuffersize:#compare buffer size
			if log_page_object.length != self.buffer_parsed.GetBufferSize():
				raise ValidationError.TestFailError(self.globalVarsObj.vtfContainer.GetTestName(), "Mismatch in buffer size! Expected: {} bytes, Actual: {} bytes for hexid {}".format(log_page_object.length, self.buffer_parsed.GetBufferSize(), hex_id))
			else:
				self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "Buffer sizes matched for id {}".format(hex_id))		

		for attribute in all_attribute:
			attribute_current_value = self.utilsObj.ReturnIntFromBuffer(
			    self.buffer_parsed, log_page_object.getAttributeByteOffset(attribute), log_page_object.getAttributeByteLength(attribute))
			log_page_object.setAttributeCurrentValue(attribute, attribute_current_value)
		return log_page_object.__dict__ if return_dict else log_page_object

	def printLogPage(self, hex_id):
		'''
		Print this log page in a nice neat format
		'''
		logObj = self.readLogPageObjectFromBuffer(hex_id)
		self.printUtilsObj.PrintLineSeparator()
		out_str = "{: <50} {: <10} {: <6} {: <30} \n\n".format("Attribute", "start:end", "#Bytes", "Value")
		for attr in logObj.attributes:
			offset, numOfBytes = logObj.attributes[attr]["byte_offset"], logObj.attributes[attr]["num_of_bytes"]
			end = offset + numOfBytes-1
			out_str += "{: <50} {: <10} {: <6} {: <30} \n".format(attr, str(offset)+":"+str(end), numOfBytes, getattr(logObj, attr))

		header = "===================================== {} {} LOG PAGE =====================================".format(hex(hex_id), logObj.log_page_name)

		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "\n{}\n{}\n{}\n".format(header, out_str, "="*len(header)))
		self.printUtilsObj.PrintLineSeparator()
