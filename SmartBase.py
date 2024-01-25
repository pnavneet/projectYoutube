##
#********************************************************************************
# @file       : SMARTBase.py
# @brief      : Module to contain SMART related variables and methods
# @author     : Barak Cohen
# @update     : Sanjeev Rai, Navneet Purohit
# @date       : 12 December2016
# @copyright (c) 2016 Western Digital Corporation or its affiliates
#********************************************************************************

import Core.ProtocolFactory as ProtocolFactory
import Lib.FWStructs.FWObjectWrapper as fwWrap
import Core.ValidationError as ValidationError
import Lib.FWStructs.VendorSMARTWrapper as SmartWrap
import Extensions.CVFImports as pyWrap
import GlobalVars
import Constants
import ErrorInjectionUtils as EIUtils
import FFUUtils
import math
import EnduranceLogUtils
import LogPageFramework #LogPageFramework

GLOBAL_AER_COUNTER = 0
GLOBAL_AER_STATUS = None

class ParseDellLog(object):
	#[Navneet] : I think we can use this class and remove dependency from VendorSmartWrapper (as it comes under CVF layer).
	#Here we can initialize the attributes based on Dell Specs.
	#dictionary containing the attributes based on Dell Spec. Key as attribute Name and value as list containing the offset and size in bytes
	#Another approach which will be more scalable and efficient is to use JSON format for different log pages (specially the vendor ones which keps changing project to project)
	dellAttributes = {
	                  'Reserved':[0, 5],
	                  'WearLevel':[5, 1],
	                  'WorstUsedReservedBlock':[6, 1],
	                  'UsedReservedBlock':[7, 1],
	                  'ReservedBlock':[8, 4],
	                  'MinimumTemperature':[12, 2],
	                  'MaximumTemperature':[14, 2],
	                  'TotalDataWrittenToNAND':[16, 16],
	                  'HostActiveIdleCounter':[32, 4],
	                  'NonOperationalPSCounter':[36, 4],
	                  'AbnormalInputVccVoltageCounter':[40, 1]
	                  #'Reserved': [41, (512-41)]
	                 }

class SmartBase(object):
	#creating SmartBase as Singleton.
	#If any test script inherits SmartBase then it won't have singleton, but if it just imports and create object instance then that will be a singleton.
	import Core.Infrastructure as Infrastructure
	__metaclass__ = Infrastructure.Singleton
	
	# @brief The constructor and initialization method for class SmartBase.
	def __init__(self, logger=None, vtfContainer=None):

		# when deviceReport=False and vtfContainer is not provided.
		if not hasattr(self, 'vtfContainer') and not vtfContainer:
			self.vtfContainer = ProtocolFactory.ProtocolFactory.createVTFContainer("NVMe")
		elif vtfContainer:
			self.vtfContainer     = vtfContainer
		self.globalVarsObj    = GlobalVars.GlobalVars(self.vtfContainer)
		self.logger           = self.globalVarsObj.logger if not logger else logger
		self.ccmObj           = self.globalVarsObj.ccmObj
		self.accessPatternObj = self.globalVarsObj.WU.accessPatternLib
		self.deviceParameter  = self.globalVarsObj.DeviceParameters
		self.sctpUtilsObj     = self.globalVarsObj.sctpUtilsObj
		self.mrphUtilsObj     = self.globalVarsObj.MRPH_Utils
		self.utilsObj         = self.globalVarsObj.utilObj
		self.idfyData         = self.globalVarsObj.identifyControllerObj.objOutputData
		self.EIutilsObj       = EIUtils.ErrorInjectionUtils()
		self.ffuUtilsObj      = FFUUtils.FFUUtils()
		self.deviceVendor     = self.utilsObj.GetDeviceVendorName()
		self.elpObj = EnduranceLogUtils.EnduranceLogUtils()
		self.logPageFrameworkObj     = LogPageFramework.LogPageFramework(self.vtfContainer)

		self.commitAction = self.globalVarsObj.randomObj.choice(range(1, self.globalVarsObj.GenericFWStructure.Morpheous_map['FFU']['CommitActionsSupported']))
		self.firmwareSlot = self.globalVarsObj.randomObj.choice(range(self.globalVarsObj.identifyControllerObj.objOutputData.FRMW.SupportedNumberOfFirmwareSlots+1))

		self.IgnoreCriticalWarningTempBit = False
		self.numOfControlSyncCounter = 0

		if self.globalVarsObj.is_sandisk_device:
			self.NandCapacity = self.deviceParameter.card_geometry_int['dieCapacity']
			self.dram, self.numOfPs, self.bicsType, self.ASIC = self.sctpUtilsObj.GetDeviceParam()

		self.deviceVendorDict = {'GENERIC': 'self.isGENERIC','DELL': 'self.isDELL', 'LENOVO': 'self.isLENOVO', 'HP': 'self.isHP',
		                         'ASUS': 'self.isASUS', 'AWS': 'self.isAWS', 'FACEBOOK': 'self.isFB', 'MSFT': 'self.isMSFT'}
		#set to False initially
		for _, variable in self.deviceVendorDict.items():
			#This will create all variables during runtime. Example self.isGENERIC, self.isDELL, self.isHP etc and value will be False. Try to print self.isGENERIC
			exec("{} = {}".format(variable, False))

		if self.deviceVendor in self.deviceVendorDict.keys():
			exec("{} = {}".format(self.deviceVendorDict[self.deviceVendor], True))
		else:
			exec("{} = {}".format(self.deviceVendorDict['GENERIC'], True))

		# SCT and SC for a command when callback is received
		self.sct = 0 ; self.sc = 0
		self.errorCountDueToEi = 0



	def ErrorHandlerFunction(self, errorGroup, errorCode) :
		'''
		    @brief : CallBack function to display StatusCode and StatusCodeType for a command which returns error
		    @input : None. arguments will get pass automatically by nvmeSession
		    @output: None
		    @usage : Call this in test script
		             self.globalVarsObj.nvmeSession.GetErrorManager().RegisterCallback(self.smartUtilsObj.ErrorHandlerFunction)
		'''
		self.errorCountDueToEi += 1
		self.sct = errorGroup
		self.sc = errorCode
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"Callback Received: Cmd return error with SCT={0} and SC={1}".format(errorGroup,errorCode))
		self.globalVarsObj.nvmeSession.GetErrorManager().ClearAllErrors()
		self.globalVarsObj.nvmeSession.GetErrorManager().DeRegisterCallback()

	# Verify that the passed in Bit is the only one that is set for CriticalWarning Byte.
	def CheckCriticalWarningByte(self, CriticalBit, enduranceCwBit=None):
		'''
		    @brief : Function to verify Critical Warning in SMART log is correctly set
		    @input : CriticalBit (or bits) (Byte-0 of SMART log), enduranceCwBit of SMART log
		    @output: None
		    @usage : Example (Available Spare) self.smartBaseObj.CheckCriticalWarningByte(CriticalBit = Constants.SMART_CONSTANTS.CriticalWarning_Spare, enduranceCwBit = self.elpObj.enduranceCwAvailableSpareBit)
			@exception: Raise exception in case of CW mis-match occurs
		'''
		smartData = self.GetSmartLogObj(pageID=Constants.SMART_PAGE_ID_GENERIC, RAE=1)
		CriticalWarningByte = getattr(smartData, 'CriticalWarning')
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "Critical Warning from SMART log is {}".format(CriticalWarningByte))
		if (CriticalWarningByte & 0xFF) != CriticalBit:
			raise ValidationError.TestFailError(self.vtfContainer.GetTestName(),"Unexpected bit changes in CriticalWarning byte, expected {} actual {}".format(CriticalBit, (CriticalWarningByte & 0xFF)))
		if self.elpObj.isEnduranceGroupSupported and enduranceCwBit != None:
			enduranceCwByte = getattr(smartData, 'EnduranceCriticalWarning')
			if (enduranceCwByte & 0xFF) != enduranceCwBit:
				raise ValidationError.TestFailError(self.vtfContainer.GetTestName(),"Unexpected bit changes in Endurance CriticalWarning byte, expected {} actual {}".format(enduranceCwBit, (enduranceCwByte & 0xFF)))

		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"Expected bit changes in CriticalWarning byte")

	def verifySmartAndEndurance(self, smartAttr, enduranceLogAttr):
		'''
		    @brief  : Function to check attribute value of SMART log and Endurance log, if same or not
		    @params : smartAttribute, enduranceLogAttribute
		    @return : None
		    @exception : Raise exception if verification fails
		'''
		if not self.elpObj.isEnduranceGroupSupported:
			self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "Endurance log is not supported. Can't perform this check.")
		else:
			attributeFromEnduranceLog = self.elpObj.getEnduranceLogPageAttributes(attribute = enduranceLogAttr)
			attributeFromSmartLog = self.GetSMARTAttribute(pageID=Constants.SMART_PAGE_ID_GENERIC, attribute=smartAttr)
			self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "{} from smart {}, from endurance log {}".format(smartAttr, attributeFromSmartLog, attributeFromEnduranceLog))
			if attributeFromSmartLog != attributeFromEnduranceLog:
				raise ValidationError.TestFailError(self.vtfContainer.GetTestName(), "{} from SMART log and Endurance log is not matching".format(smartAttr))
			else:
				self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "{} from smart and endurance log matches".format(smartAttr))

	# Reading Max PEC values for SLC and TLC/QLC
	def Read_PEC_Threshold(self):

		ftl_config_set = self.globalVarsObj.FTL_info.CFG_SetNumbers_e["PS_MRPH_FTL"]
		ftl_buff = self.sctpUtilsObj.ReadConfigSet(ConfSet=ftl_config_set, secCount=1, verbose=True)
		ftl_buff.PrintToLog()
		slc_max_pec_offset = 8
		mlc_max_pec_offset = 12
		self.TLC_PEC_THRSLD = ftl_buff.GetFourBytesToInt(mlc_max_pec_offset)
		self.SLC_PEC_THRSLD  = ftl_buff.GetFourBytesToInt(slc_max_pec_offset)
		#Verification of CAL2BLUE-875, As per FW TLC Max PE Cycles': u'3000', 'SLC Max PE Cycles': u'100000'
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "TLC threshold value = {0} ".format(self.TLC_PEC_THRSLD))
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "SLC threshold value = {0} ".format(self.SLC_PEC_THRSLD))

		return self.SLC_PEC_THRSLD, self.TLC_PEC_THRSLD


	##
	# @ brief A method to return SMART log object
	# @ param pageID (SMARTgeneric = 0x02, SMARTDELL = 0xCA ,SMARTLENOVO = 0XDF,ErrorInformation = 0x1,
	#                Firmware Slot Information = 0x3,Changed Namespace List = 0x4,CommandEffectsLog = 0x5)
	# @ exception Fails if GetLogPage command fails
	def GetSmartLogObj(self, pageID, RAE=1, PrintBuff=False, returnDictionary=False):
		if not self.vtfContainer.cmd_mgr.WaitForThreadCompletion():
			raise ValidationError.CVFGenericExceptions("GetSmartLogObj", "WaitForCompletion Failed")

		if pageID in  (Constants.SMART_PAGE_ID_GENERIC, Constants.SMART_PAGE_ID_DELL, Constants.ERROR_INFORMATION_PAGE_ID):
			# if supported in Log Page Framework, use it to parse log pages
			# plan is to transfer all log pages to use this framework
			smartObj = self.logPageFrameworkObj.readLogPageObjectFromBuffer(hex_id=pageID, RAE=RAE, return_dict=returnDictionary)
			return smartObj

		smartBuffer = self.ccmObj.GetLogPageNVMe(pageID,NS_ID=0xFFFFFFFF, RAE=RAE, sendType = pyWrap.SEND_IMMEDIATE)
		# Printing the SMART Buffer for debug purpose during any failure
		if PrintBuff:
			smartBuffer.PrintToLog()

		# API to Parse Facebook Log Page 0xFB buffer
		if pageID in [Constants.SMART_PAGE_ID_FB, Constants.SMART_PAGE_ID_MSFT_C0]:
			smartObj = self.Parse_Log_Page(smartBuffer, pageID)

		elif (pageID == Constants.SMART_PAGE_ID_AWS)  or (pageID == Constants.SMART_PAGE_ID_AWS_GOEM):
			smartObj = SmartWrap.CreateSMARTFromAWSBuffer(smartBuffer, pageID)

		else:
			smartObj = SmartWrap.CreateSMARTFromBuffer(smartBuffer, pageID)

		return smartObj.__dict__ if returnDictionary else smartObj


	##
	# @ brief A method to return SMART log object
	# @ param pageID (SMARTgeneric = 0x02, SMARTDELL = 0xCA ,SMARTLENOVO = 0XDF,ErrorInformation = 0x1,
	#                Firmware Slot Information = 0x3,Changed Namespace List = 0x4,CommandEffectsLog = 0x5)
	# @ exception Fails if GetLogPage command fails
	def GetSmartRawLogObj(self,pageID,RAE=1):
		smartBuffer = self.ccmObj.GetLogPageNVMe(pageID,NS_ID=0xFFFFFFFF, RAE=RAE, sendType = pyWrap.SEND_IMMEDIATE)
		#create object from buffer using VTF parser
		return(smartBuffer)

	# Verify event is not masked by setFeature or log page
	# Mask the corresponding bits with the appropriate bit to sending the AER.
	def VerifyEventNotMask(self, mask=0xf):
		self.ccmObj.SetFeatureAER(mask)  #Asynchronous Event Configuration
		self.ccmObj.WaitForThreadCompletion()
		warningFlags = self.ccmObj.GetFeatureAER()
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"Warning Flags = {}".format(warningFlags))
		warningByteSMART = self.GetSMARTAttribute(Constants.SMART_PAGE_ID_GENERIC, "CriticalWarning", RAE=0)

		# Verfiy AER is set and No Critical Warning bit is set
		if warningFlags != mask or warningByteSMART:
			raise ValidationError.TestFailError("SMART Utils Event Verification", "AER SET feature or SMART clear events is not functioning correctly. AER critical byte value is {0}, SMART Critical Warning byte value = {1}".format(warningFlags, warningByteSMART))
		else:
			self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "AER set feature is completed and No outstanding SMART events")


	#Register AER Request
	def IssueAerRequest(self):
		try:
			self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"Issuing AER from SMARTBase.IssueAerRequest()")
			objAER = pyWrap.AsyncEventReq(self.AERCallBack)
			self.globalVarsObj.vtfContainer.cmd_mgr.PostRequestToWorkerThread(objAER)
			self.ccmObj.WaitForThreadCompletion()
		except  ValidationError.CVFExceptionTypes ,exc:
			raise ValidationError.TestFailError("AER req", GlobalVars.FVTExcPrint()+str(exc))
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"AER sent successfully ")


	def AERCallBack(self,DWORD0):
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "Callback function invoked with AEN as {}".format(DWORD0))
		global GLOBAL_AER_STATUS
		global GLOBAL_AER_COUNTER
		GLOBAL_AER_STATUS = DWORD0
		GLOBAL_AER_COUNTER += 1
		return 0 #CVF-12269, CVF-12253,CVF 3.03.75 onwards return (0 for success) / (1 for failure).


	##
	# @brief This method verify test result by comparing expected value to SMART log value.
	# @param : smartData - data counter from log
	# @param   expectedResult - expected value from test
	# @param   gapAllowed - legal gap between counters
	def VerifyTestResult(self, smartData, expectedResult, gapAllowed=0, massage=" "):
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "Verify test result")
		if self.globalVarsObj.isUnitTest:
			return
		gapBetweenResult = abs(smartData - expectedResult)
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "SMART Data is %d and Expected Data is %d"%(smartData, expectedResult))
		if (gapBetweenResult > gapAllowed):
			raise ValidationError.TestFailError(self.vtfContainer.GetTestName(),
			                                    "%s - The difference between the expected data and the the actual is: %d (expected %d and actual %d)"%(massage,gapBetweenResult,expectedResult,smartData))

	##
	# @brief This method use to return requsted attribute value from SMART log selected with pageID .
	# @param : attribute(string)- SMART attribute name according to the names in VendorSMARTWrapper.py
	# @param : pageID - generic/ DELL / LENOVO
	# @param : RAE(Retain Asynchronous Event) - 0:Clear the Asynchronous Event after the command completes successfully
	#                                           1:Retain the Asynchronous Event after the command completes successfully
	def GetSMARTAttribute(self, pageID, attribute, RAE=1, PrintBuff=True):
		self.WaitForThreadCompletion()
		smartObj = self.GetSmartLogObj(pageID, RAE, PrintBuff)
		return getattr(smartObj, attribute)


	##
	# @brief This method to set coposite Temperature
	# @param - required temp
	def SetCompositeTemp(self, temp):
		# Navneet 9/15/2021 : added this function in ccm so that can be used in other test scripts.
		self.ccmObj.SetCompositeTemp(temp)

	# @ brief This method to change power mode
	# @ param - powestate - if "high" change to high if "low" to low
	def ChangePowerMode(self,powerState="high"):
		# Navneet 6/15/2021 : adding few lines to support this code. Will remove this function after code review. SMART115 and Telemetry09 uses this function.
		# NonOperational Power State list : For given PowerState if NOPS bit is 1, it's an NOPS
		self.lowPwrState = [i for i in range(len(self.idfyData.PSDx)) if self.idfyData.PSDx[i].NOPS]
		#Operational Power State list : PS which are not in above list and for which ACTP or MP is non zero
		self.highPwrState = [i for i in range(len(self.idfyData.PSDx)) if i not in self.lowPwrState and self.idfyData.PSDx[i].ACTP]

		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "change power state !!")
		if(powerState=="high"):
			powerState = 0
			self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "Sending Set Features to enter: %d"%powerState)
			self.ccmObj.SetFeaturesPwrMgmt(powerState=powerState)
			self.ccmObj.WaitForThreadCompletion()
		elif(powerState=="low"):
			powerState = self.globalVarsObj.randomObj.choice(self.lowPwrState)
			self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "Sending Set Features to enter: %d"%powerState)
			self.ccmObj.SetFeaturesPwrMgmt(powerState=powerState)
			self.ccmObj.WaitForThreadCompletion()

	def GetFeatureTemp(self):
		# Navneet 6/15/2021 : ccm already has this function
		return self.ccmObj.GetFeatureTemp()

	def SetFeatureAER(self, criticalWarningByte, save = False, NS_ID = 0xFFFFFFFF):
		# Navneet 6/15/2021 : ccm already has this function
		self.ccmObj.SetFeatureAER(criticalWarningByte=criticalWarningByte, save=save, NS_ID=NS_ID)

	def GetFeatureAER(self):
		# Navneet 6/15/2021 : ccm already has this function
		return self.ccmObj.GetFeatureAER()

	def WaitForThreadCompletion(self):
		self.ccmObj.WaitForThreadCompletion()

	# Navneet : 6/15/2021 : There exists a method in SCTP to get this info. Using that method instead. Please refer while using this.
	def getMAXANDAVGPEC(self, option, metaDieID, partition=None, numMetaBlockInMetaDie=None, returnDict=False, metaBlockNumber=None, verbose = True):
		return self.sctpUtilsObj.SCTPGetPECycle(option=option,metaDieID=metaDieID,partition=partition, numMetaBlockInMetaDie=numMetaBlockInMetaDie, returnDict=returnDict, metaBlockNumber=metaBlockNumber, verbose=verbose)


	def GetDellSMARTAttribute(self, smartAttr, returnDict=False):
		'''
		    @brief  : to calculate spares, PF, EF total and worst component
		    @input  : Dell smartAttr
		    @return : value of specified Dell smartAttr, if returnDict=True , will return entire dictionary of Dell SMART attributes
		    @author : Navneet
		    @Note   : This function will also be used to return availableSpares (generic NVMe attribute)
		'''
		#Initialize variables to 0
		totalPfCount = totalEfCount = worstPfCount = worstEfCount = 0
		pfCountNormalized = efCountNormalized = 0
		reservedBlockCnt = self.globalVarsObj.reservedBlockCnt

		self.PS_Spares = {}

		# MSFT related for Raw Bad Block attribute value
		MSFT_SmartAtt = {"Raw_BB":0}

		#dictionary to hold values
		dellSmartAttr = {"ReAssignedSectors":0,
		                 "PF":0,
		                 "PFTotal":0,
		                 "EF":0,
		                 "EFTotal":0,
		                 "WearLevelingCount":0,
		                 "WorstUsedReservedBlock":0,
		                 "UsedReservedBlock_SSD_Total":0,
		                 "ReservedBlockCount":self.globalVarsObj.reservedBlockCnt}

		#get FTL spares per MD and minSpareCount
		ftlSparesPerMD = self.sctpUtilsObj.GetFTLSpares(returnDict=True)
		#below minSpareCount code based on FW hardcoded value
		if self.globalVarsObj.bicsType == 3:
			minSpareCount = 6
		else:
			ParsedFTLFormatConfigObj, _ = self.sctpUtilsObj.GetFTLConfiguration(verbose=False)
			minSpareCount = ParsedFTLFormatConfigObj.FTLFormatConfig_s.minSparesRequiredPerMetadie

		#assigning worstSpareCount as minSpareCount which is default threshold
		worstSpareCount = minSpareCount

		#get BBM table to calculate PS spares (PF, EF, spare)
		bbmTable       = self.utilsObj.getRelinkTables(returnDict=True)

		#Below mentioned values can also be obtained from bbmTable
		numPs     = self.globalVarsObj.numOfPs
		fimsPerPs = self.globalVarsObj.DeviceParameters.No_of_channel/numPs
		mdPerPs   = self.globalVarsObj.numOfMetaDiePerJB/numPs
		numPlanes = self.globalVarsObj.DeviceParameters.Planes_Per_Physical_Block

		#Handle sparesPerPlane calculation for SLC only, SLC-TLC, SLC-QLC products. (below method is generic and can be applicable for any products)
		#First get a list which will give info on whether bbmTable reports spare for SLC only, SLC-TLC, SLC-QLC
		bbmSpareList = [i for i in dir(bbmTable["PS0parsed"].BBM_Counters[0].spare) if not i.startswith('_')] #here we can use PS-0 and phyPlane as 0, since list will be same for PS-1 as well when applicable
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "smartTest: following is bbm spare list {}".format(bbmSpareList))

		#Get the value of PF, EF, Spares per Plane and update worst PF/EF , total PF/EF and other attributes accordingly.
		for ps in range(numPs):
			whichPsToParse = 'PS{}parsed'.format(ps)
			for fimInPs in range(fimsPerPs):
				for mdInPs in range(mdPerPs):
					for plane in range(numPlanes):
						#Calculate physical plane to get BBM counters
						phyPlane = (fimInPs * numPlanes) + (mdInPs * fimsPerPs * numPlanes)+plane
						#SparesPerPlane calculation : (numPs*mdInPs+ps : to generate values from 0 to totalMetaDiesInDevice)
						sparesPerPlane = ftlSparesPerMD[numPs*mdInPs+ps] + sum([getattr(bbmTable[whichPsToParse].BBM_Counters[phyPlane].spare, bbmSpareList[i]) for i in range(len(bbmSpareList))])
						#PFPerPlane, EFPerPlane Calculation
						pfPerPlane = bbmTable[whichPsToParse].BBM_Counters[phyPlane].errTypeCnt.PFCnt
						efPerPlane = bbmTable[whichPsToParse].BBM_Counters[phyPlane].errTypeCnt.EFCnt + \
						    bbmTable[whichPsToParse].BBM_Counters[phyPlane].errTypeCnt.UECCCnt

						#print values for debug purpose
						self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "smartTest : ps-{}, fimInPs-{}, mdInPs-{}, plane-{}, phyPlane-{}"
						                               .format(ps, fimInPs, mdInPs, plane, phyPlane))
						self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "smartTest : sparesPerPlane : {}, pfPerPlane : {}, efPerPlane : {}"
						                               .format(sparesPerPlane, pfPerPlane, efPerPlane))

						# For getting the sparesperPlane of all planes for MSFT C0 log Page Badblock Raw count calculation
						if sparesPerPlane < minSpareCount:

							self.PS_Spares[phyPlane] = sparesPerPlane

						#Calculate worst and normalized values
						if minSpareCount < sparesPerPlane:
							reservedBlockCnt += minSpareCount
						else:
							#Case when sparesPerPlane is less than SPARE Threshold (minSpareCount) and there are grown defects
							worstSpareCount = sparesPerPlane if worstSpareCount > sparesPerPlane else worstSpareCount
							reservedBlockCnt += sparesPerPlane
							pfCountNormalized = self.Roundup((pfPerPlane * (minSpareCount - sparesPerPlane)), (pfPerPlane + efPerPlane))
							efCountNormalized = minSpareCount - sparesPerPlane - pfCountNormalized
							totalPfCount += pfCountNormalized
							totalEfCount += efCountNormalized
							worstPfCount = pfCountNormalized if worstPfCount < pfCountNormalized else worstPfCount
							worstEfCount = efCountNormalized if worstEfCount < efCountNormalized else worstEfCount

		#totalPlanes is calculated as totalFimsPerPs (or dies Per MetaDie) (4) * planesPerDie (2) * numMetaDies (varies according to device and die capacity)
		totalPlanes = fimsPerPs * numPlanes * self.globalVarsObj.numOfMetaDiePerJB

		#print for debug purpose
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "smartTest : totalPfCount {}, totalEfCount {}, worstPfCount {}, worstEfCount {}, totalPlanes {}"
		                               .format(totalPfCount, totalEfCount, worstPfCount, worstEfCount, totalPlanes))

		#AvailableSpare attribute
		if smartAttr.lower() == "availablespare":
			self.globalVarsObj.Available_Spare = self.getSparePercent(worstSpareCount, minSpareCount)
			return self.globalVarsObj.Available_Spare
		elif smartAttr in dellSmartAttr.keys():
			#Update Dell attributes as well as GlobalVars attribute (based on oneFVT PR 3694)
			self.globalVarsObj.ReAssigned_Sectors = dellSmartAttr['ReAssignedSectors'] = 100 - self.getSparePercent(worstSpareCount, minSpareCount)
			self.globalVarsObj.Worst_Program_Fail = dellSmartAttr['PF']                = self.Roundup((100 * worstPfCount), minSpareCount)
			self.globalVarsObj.Program_Fail_Total = dellSmartAttr['PFTotal']           = self.Roundup((100 * totalPfCount), (minSpareCount * totalPlanes))
			self.globalVarsObj.Worst_Erase_Fail   = dellSmartAttr['EF']                = self.Roundup((100 * worstEfCount), minSpareCount)
			self.globalVarsObj.Erase_Fail_Total   = dellSmartAttr['EFTotal']           = self.Roundup((100 * totalEfCount), (minSpareCount * totalPlanes))
			#dellSmartAttr['WearLevelingCount']                    = "TBD" #calculated based on PEC. Handled separately in test.
			#same as reAssignedSectorCount
			self.globalVarsObj.Worst_Used_Resevred_Block = dellSmartAttr['WorstUsedReservedBlock']      = 100 - self.getSparePercent(worstSpareCount, minSpareCount)
			self.globalVarsObj.Used_Resevred_Block_Total = dellSmartAttr['UsedReservedBlock_SSD_Total'] = self.Roundup((100 * (totalPfCount+totalEfCount)), minSpareCount*totalPlanes)
			self.globalVarsObj.reservedBlockCnt = dellSmartAttr['ReservedBlockCount']                   = reservedBlockCnt
			return (dellSmartAttr) if returnDict else (dellSmartAttr[smartAttr])

		elif smartAttr in MSFT_SmartAtt.keys():
			return self.PS_Spares

		else:
			raise ValidationError.TestFailError(self.vtfContainer.GetTestName(), "Invalid SMART attribute to this function")


	def getSparePercent(self, curerntWorstSpareCount, minimumSpareCountReqPerMetaDie):
		"""This function returns the available spare percentange based on currentWorstSpareCountPerMetaDie and minimumSpareCountRequiredPerMetaDie
		NOTE    : This varies across projects and BiCS type. No standard formula applies for all projects. Creates dependency from FW side.
		Example :
				Atlas, Atlas-R    availableSparePercentage goes from 100 -> 75 -> 50 -> 25 -> 4 -> 0
				ZNS      availableSparePercentage goes from 100 -> 99 -> 98 -> 97 .... 0 (just for reference. ZNS has separate code base.)
				Hermes 2, Vulcan, Clover availableSparePercentage was calculated -> currentWorstSpareCount / minimumSpareCountRequiredPerMetaDie (Except for worstSpareCount as 1)
				(based on FVT feedback, observations)
		"""
		maxAvailableSparePercentage = 100 #100% available spare
		# Handling for Atlas as FW hardcodes the value of availableSpare to be returned based on currentWorstSpareCount
		# Atlas-R changed the design to follow other projects. Reference : ATLASR-2564
		if self.globalVarsObj.GenericFWStructure.Morpheous_map['Generic']['Json_Product_Name'] in ['Atlas']:
			availableSparePercentageDict = {5:100, 4:75, 3:50, 2:25, 1:4, 0:0} #hardcoded from FW only
			return availableSparePercentageDict[curerntWorstSpareCount]
		else:
			availableSparePercentageDict = {1:4, 0:0} #hardcoded for few values from FW only.

		# For rest of the projects, where FVT has understanding that AvailableSparePercentage is calculated based on formula mentioned in function description.
		if curerntWorstSpareCount >= minimumSpareCountReqPerMetaDie:
			return maxAvailableSparePercentage
		elif curerntWorstSpareCount == 1:
			return availableSparePercentageDict[curerntWorstSpareCount]
		else:
			return int(math.ceil(curerntWorstSpareCount / float(minimumSpareCountReqPerMetaDie) * 100))

	def getSpareMetdie(self, dataBuffer):
		self.numOfmetadies = self.globalVarsObj.metaDiesPerZone
		self.sparePerMetadie = {}
		for i in range(self.numOfmetadies):
			self.sparePerMetadie[i]=dataBuffer.GetFourBytesToInt((i+1)*4)
		return self.sparePerMetadie

	def VerifyEvent(self, event):

		global GLOBAL_AER_COUNTER
		global GLOBAL_AER_STATUS

		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "GLOBAL_AER_COUNTER = {0}".format(GLOBAL_AER_COUNTER))
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "GLOBAL_AER_STATUS  = {0}".format(GLOBAL_AER_STATUS))

		if GLOBAL_AER_COUNTER == 0:
			raise ValidationError.TestFailError(self.vtfContainer.GetTestName(), "AEN didn't occur after SMART event {0} and AER status = {1} ".format(event, GLOBAL_AER_STATUS))

		if event == "AvailableSpare":
			AsynEventInfo = Constants.SMART_CONSTANTS.AsyncEventInformation_Spare
		elif event == "TemperatureThreshold":
			AsynEventInfo = Constants.SMART_CONSTANTS.AsyncEventInformation_Temperature
		elif event == "PercentageUsedHP" or event == "Reliability":
			AsynEventInfo = Constants.SMART_CONSTANTS.AsyncEventInformation_PercentageUsedHP
		else:
			AsynEventInfo = Constants.SMART_CONSTANTS.AsyncEventInformation_Reliability

		# Parse AER DWORD0
		asyncEventType = (GLOBAL_AER_STATUS & 0x7)  # Check SMART event type(001) from "Asynchronous Event Type" field
		asyncEventInformation = (GLOBAL_AER_STATUS >> 8) & 0xFF  # Check for SMART event info from "Asynchronous Event Information" field
		logPageIdentifier = (GLOBAL_AER_STATUS >> 16) & 0xFF  # Check log page associated
		if (asyncEventType != 0x1 or asyncEventInformation != AsynEventInfo or logPageIdentifier != 0x2):
			raise ValidationError.TestFailError(self.vtfContainer.GetTestName(),
							    "DWORD 0 from AER call back doesn't match to smart Avalaible spare event, asyncEventType is {0} asyncEventInformation is {1} logPageIdentifier is {2}".format(asyncEventType, asyncEventInformation, logPageIdentifier))

	# Method to get EI Statistics
	def GetErrHandlingCounters(self):
		# Navneet 6/15/2021 : Keeping this here just to support old code.
		return self.GetErrCounters()

	def GetErrCounters(self,EIType="all"):
		# Navneet 6/15/2021 : Updating the code to remove if else, based on numPS

		#dictionary to hold different error types
		self.eiDict = {"PF": "self.countPf", "EF": "self.countEf", "xorUECC": "self.xorFatalUECC",
		               "ugsdUECC": "self.ugsdFatalUECC", "wucFatalUECC": "self.wucFatalUECC",
		               "sgdPFCount": "self.sgdPFCount", "relinkUECCList": "self.relinkUECCList",
		               "softECC": "self.softECC", "xorRecovery": "self.xorRecovery"}

		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"Get Error Handling Counters")
		self.stats = self.sctpUtilsObj.GetErrorHandlingStatistics()
		self.sctpParsedObj = fwWrap.FWDiagCustomObject(self.stats, "EH_ErrorCounterXML_s")

		# Initialize the attribute values with 0
		self.countPf = self.countEf = self.xorFatalUECC = self.ugsdFatalUECC = self.wucFatalUECC = self.sgdPFCount = self.relinkUECCList = self.softECC = self.xorRecovery = 0
		for i in range(self.globalVarsObj.numOfPs):
			self.countPf += eval("self.sctpParsedObj.EH_ErrorCounterXML_s.PS{}.programFailure".format(i))
			self.countEf += eval("self.sctpParsedObj.EH_ErrorCounterXML_s.PS{}.eraseNAND_Failure".format(i))
			self.xorFatalUECC += eval("self.sctpParsedObj.EH_ErrorCounterXML_s.PS{}.xorFatalUECC".format(i))
			self.ugsdFatalUECC += eval("self.sctpParsedObj.EH_ErrorCounterXML_s.PS{}.ugsdFatalUECC".format(i))
			self.wucFatalUECC += eval("self.sctpParsedObj.EH_ErrorCounterXML_s.PS{}.wucFatalUECC".format(i))
			try:
				self.sgdPFCount += eval("self.sctpParsedObj.EH_ErrorCounterXML_s.PS{}.sgdSGDLowtailOverProgram".format(i))
			except:
				self.sgdPFCount = 0
			self.relinkUECCList += eval("self.sctpParsedObj.EH_ErrorCounterXML_s.PS{}.relinkFromUECCList".format(i))
			# Navneet: based on oneFVT PR 3694, commenting this out, as couldn't find softECC attribute in EH_ErrorCounterXML_s.PS0 for Cal-x2. Sanjeev to check and update in different PR
			#self.softECC += eval("self.sctpParsedObj.EH_ErrorCounterXML_s.PS{}.softECC".format(i))
			# below is a list, and hence need to perform sum of all elements of list.
			self.xorRecovery += sum(eval("self.sctpParsedObj.EH_ErrorCounterXML_s.PS{}.rehXorRecoveryCount[0:-1]".format(i)))

		if EIType == "all":
			return self.countPf,self.countEf,self.xorFatalUECC,self.ugsdFatalUECC,self.wucFatalUECC #Not changing this line, as it will break the existing tets which calls self.GetErrHandlingCounters() API
		else:
			try:
				return(eval(self.eiDict[EIType]))
			except Exception as e:
				raise ValidationError.TestFailError(self.vtfContainer.GetTestName(), "Invalid Error Counter specified or Error count key {} does not exists. {}"
				                                    .format(EIType, e.message))

	def GetElAttribute(self,attribute):
		self.WaitForThreadCompletion()
		errorLogObj = self.GetErrorLogObj(Constants.ERROR_INFORMATION_PAGE_ID)
		return getattr(errorLogObj, attribute)

	##
	# @ brief A method to return Error log object
	# @ exception Fails if GetLogPage command fails
	# @param - numOfErrors to retrieve
	def GetErrorLogObj(self,numOfEntries=1):
		errorLogBuffer = self.ccmObj.GetLogPageNVMe(Constants.ERROR_INFORMATION_PAGE_ID,0xFFFFFFFF,numOfEntries)
		#create object from buffer using VTF parser
		errorLogObj = SmartWrap.CreateSMARTFromBuffer(errorLogBuffer, Constants.ERROR_INFORMATION_PAGE_ID)
		return(errorLogObj)


	def GetSMARTExpectedAttribute(self,smartAttr):
		# Navneet : 6/15/2021 : This function is only being used by Dell log page attributes. Hence calling that function only.
		Expected_SMART = self.GetDellSMARTAttribute(smartAttr)
		# Navneet : 6/15/2021 : Will check with Sanjeev if below code (setting attributes to 0) is needed or not.
		self.globalVarsObj.reservedBlockCnt=0
		self.globalVarsObj.totalEFCount=0
		self.globalVarsObj.totalPFCount=0
		self.globalVarsObj.worstsparecount=100
		self.globalVarsObj.worstPFCount = 0
		self.globalVarsObj.worstEFCount = 0

		return Expected_SMART

	def Roundup(self, dividend, divisor):
		return ((dividend + (divisor/2)) / divisor)

	def Average(self, list):
		return sum(list) / len(list)

	# API to Read the PEC count across all Metadies
	# returns: slc_avg, slc_max, slc_min, tlc_avg, tlc_max, tlc_min
	def GetPECount(self):
		self.noOfMetadie = self.globalVarsObj.metaDiesPerZone

		self.slc_pec_avg_list = []
		self.slc_pec_max_list = []
		self.slc_pec_min_list = []
		self.tlc_pec_avg_list = []
		self.tlc_pec_max_list = []
		self.tlc_pec_min_list = []

		# Read Avg, Min and Max PEC values across all MetaDie and store it in list
		for md in range(self.noOfMetadie):
			""" Get the expected Avg,Max,Min PEC for SLC partition  """
			slc_pec_avg, slc_pec_max, slc_pec_min  = self.getMAXANDAVGPEC(Constants.SCTP_CONSTANTS.SCTP_GETPE_MAXAVG,metaDieID = md, partition = 0x0,returnDict=True,metaBlockNumber = 0x0)
			self.WaitForThreadCompletion()

			self.slc_pec_avg_list.append(slc_pec_avg)
			self.slc_pec_max_list.append(slc_pec_max)
			self.slc_pec_min_list.append(slc_pec_min)

			""" Get the expected Avg,Max,Min PEC for TLC partition  """
			tlc_pec_avg, tlc_pec_max, tlc_pec_min  = self.getMAXANDAVGPEC(Constants.SCTP_CONSTANTS.SCTP_GETPE_MAXAVG,metaDieID = md, partition = 0x1,returnDict=True,metaBlockNumber = 0x0)
			self.WaitForThreadCompletion()

			self.tlc_pec_avg_list.append(tlc_pec_avg)
			self.tlc_pec_max_list.append(tlc_pec_max)
			self.tlc_pec_min_list.append(tlc_pec_min)

		SLC_PEC_AVG_ALLMetaDie = int(self.Average(self.slc_pec_avg_list))
		SLC_PEC_MAX_ALLMetaDie = int(self.Average(self.slc_pec_max_list))
		SLC_PEC_MIN_ALLMetaDie = int(self.Average(self.slc_pec_min_list))
		TLC_PEC_AVG_ALLMetaDie = int(self.Average(self.tlc_pec_avg_list))
		TLC_PEC_MAX_ALLMetaDie = int(self.Average(self.tlc_pec_max_list))
		TLC_PEC_MIN_ALLMetaDie = int(self.Average(self.tlc_pec_min_list))

		#-----------------------------------------------------------------------------------------------------
		# Polarion Requirement
		# VULCAN-7962, VULCAN-8194
		# DUI Avg SLC & TLC PEC value verification with SCTP data

		#Getting DUI
		try:
			DUI_PEC_DataObj=self.utilsObj.GetDUILogSection(sectionName="DUI_Section_StaticUnitInfo")

			DUI_PEC_AVG_TLC = DUI_PEC_DataObj.staticUnitInfo.avgMLCHotCount
			DUI_PEC_AVG_SLC = DUI_PEC_DataObj.staticUnitInfo.avgSLCHotCount

			#Print DUI and SCTP Values
			self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "DUI_PEC_AVG_TLC  = {0}, DUI_PEC_AVG_SLC  = {1}".format(DUI_PEC_AVG_TLC, DUI_PEC_AVG_SLC))
			self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "SCTP_PEC_AVG_TLC = {0}, SCTP_PEC_AVG_SLC = {1}".format(TLC_PEC_AVG_ALLMetaDie, SLC_PEC_AVG_ALLMetaDie))

			# Compare TLC_AVG_PEC
			if DUI_PEC_AVG_TLC != TLC_PEC_AVG_ALLMetaDie:
				raise ValidationError.TestFailError(self.globalVarsObj.vtfContainer.GetTestName(), "Mismatch in PEC, DUI_PEC_AVG_TLC = {0}, SCTP_PEC_AVG_TLC = {1}".format(DUI_PEC_AVG_TLC, TLC_PEC_AVG_ALLMetaDie))

			# Compare SLC_AVG_PEC
			if DUI_PEC_AVG_SLC != SLC_PEC_AVG_ALLMetaDie:
				raise ValidationError.TestFailError(self.globalVarsObj.vtfContainer.GetTestName(), "Mismatch in PEC, DUI_PEC_AVG_SLC = {0}, SCTP_PEC_AVG_SLC = {1}".format(DUI_PEC_AVG_SLC, SLC_PEC_AVG_ALLMetaDie))
		except Exception as e:
			self.logger.Info(self.globalVarsObj.TAG, "Attributes does not exists in the DUI log for given program, {}".format(e.message))

		#---------------------------------------------------------------------------------------------------


		return SLC_PEC_AVG_ALLMetaDie, SLC_PEC_MAX_ALLMetaDie, SLC_PEC_MIN_ALLMetaDie, TLC_PEC_AVG_ALLMetaDie, TLC_PEC_MAX_ALLMetaDie, TLC_PEC_MIN_ALLMetaDie

	##
	# @brief This method use check the critical warning byte the reliability bit is set.
	# @param : None
	def verifyReliabilityBit(self):
		self.checkFlag	= False
		warningByteSMART = self.GetSMARTAttribute(Constants.SMART_PAGE_ID_GENERIC, "CriticalWarning")

		#Verify warningByteSMART bit_3 is set
		if (warningByteSMART & 0x4) :
			self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"ReliabilityBit bit is SET to 1, warningByteSMART = {0}".format(warningByteSMART))
			self.checkFlag=True

		return  self.checkFlag


	def Parse_Log_Page(self, buffer_parsed, pageID):

		AttributeDict = {}

		#Facebook Log page parsing Structure
		#------------------------------------------------------------------------------------------------------------
		if pageID == Constants.SMART_PAGE_ID_FB:

			AttributeDict['PhysicalMediaUnitsWrittenTLC']       =  self.ccmObj.GetNBytesToInt(buffer_parsed,0,16)
			AttributeDict['PhysicalMediaUnitsWrittenSLC']       =  self.ccmObj.GetNBytesToInt(buffer_parsed,16,16)
			AttributeDict['BadUserNANDBlock_Normalized']        =  self.ccmObj.GetNBytesToInt(buffer_parsed,32,2)
			AttributeDict['BadUserNANDBlock_Raw']               =  self.ccmObj.GetNBytesToInt(buffer_parsed,34,6)
			AttributeDict['XORRecoverycount']                   =  self.ccmObj.GetNBytesToInt(buffer_parsed,40,8)
			AttributeDict['UncorrectableReadErrorCount']        =  self.ccmObj.GetNBytesToInt(buffer_parsed,48,8)
			AttributeDict['SSDE2E_CorrectedErrors']             =  self.ccmObj.GetNBytesToInt(buffer_parsed,56,8)
			AttributeDict['SSDE2E_DetectedErrors']              =  self.ccmObj.GetNBytesToInt(buffer_parsed,64,4)
			AttributeDict['SSDE2E_UncorrectedErrors']           =  self.ccmObj.GetNBytesToInt(buffer_parsed,68,4)
			AttributeDict['PercentageUsed_System']              =  self.ccmObj.GetNBytesToInt(buffer_parsed,72,1)
			AttributeDict['MinPECTLC']                          =  self.ccmObj.GetNBytesToInt(buffer_parsed,73,8)
			AttributeDict['MaxPECTLC']                          =  self.ccmObj.GetNBytesToInt(buffer_parsed,81,8)
			AttributeDict['MinPECSLC']                          =  self.ccmObj.GetNBytesToInt(buffer_parsed,89,8)
			AttributeDict['MaxPECSLC']                          =  self.ccmObj.GetNBytesToInt(buffer_parsed,97,8)
			AttributeDict['PF_Normalized']                      =  self.ccmObj.GetNBytesToInt(buffer_parsed,105,2)
			AttributeDict['PF_Raw']                             =  self.ccmObj.GetNBytesToInt(buffer_parsed,107,6)
			AttributeDict['EF_Normalized']                      =  self.ccmObj.GetNBytesToInt(buffer_parsed,113,2)
			AttributeDict['EF_Raw']                             =  self.ccmObj.GetNBytesToInt(buffer_parsed,115,6)
			AttributeDict['PCIeCorrectableErrorcount']          =  self.ccmObj.GetNBytesToInt(buffer_parsed,121,8)
			AttributeDict['%FreeBlocks_User']                   =  self.ccmObj.GetNBytesToInt(buffer_parsed,129,1)
			AttributeDict['SecurityVersionNumber']              =  self.ccmObj.GetNBytesToInt(buffer_parsed,130,8)
			AttributeDict['%FreeBlocks_System']                 =  self.ccmObj.GetNBytesToInt(buffer_parsed,138,1)
			AttributeDict['TRIM_Completions_count']             =  self.ccmObj.GetNBytesToInt(buffer_parsed,139,16)
			AttributeDict['TRIM_InCompletion_MB']               =  self.ccmObj.GetNBytesToInt(buffer_parsed,155,8)
			AttributeDict['TRIM_Completion_%age']               =  self.ccmObj.GetNBytesToInt(buffer_parsed,163,1)
			AttributeDict['BackgroundBack-PressureGauge']       =  self.ccmObj.GetNBytesToInt(buffer_parsed,164,1)
			AttributeDict['SoftECCerrorcount']                  =  self.ccmObj.GetNBytesToInt(buffer_parsed,165,8)
			AttributeDict['Refreshcount']                       =  self.ccmObj.GetNBytesToInt(buffer_parsed,173,8)
			AttributeDict['BadSystemNANDBlock_Normalized']      =  self.ccmObj.GetNBytesToInt(buffer_parsed,181,2)
			AttributeDict['BadSystemNANDBlock_Raw']             =  self.ccmObj.GetNBytesToInt(buffer_parsed,183,6)
			AttributeDict['EnduranceEstimate']                  =  self.ccmObj.GetNBytesToInt(buffer_parsed,189,16)
			AttributeDict['TT_Status']                          =  self.ccmObj.GetNBytesToInt(buffer_parsed,206,1)
			AttributeDict['TT_Count']                           =  self.ccmObj.GetNBytesToInt(buffer_parsed,205,1)
			AttributeDict['Unaligned_IO']                       =  self.ccmObj.GetNBytesToInt(buffer_parsed,207,8)
			AttributeDict['PhysicalMediaUnitsRead']             =  self.ccmObj.GetNBytesToInt(buffer_parsed,215,16)
			AttributeDict['LogPageVersion']                     =  self.ccmObj.GetNBytesToInt(buffer_parsed,510,2)

			if AttributeDict['SecurityVersionNumber'] != 1:
				raise ValidationError.TestFailError("FB", "FB Log Page Attribute SecurityVersionNumber is not set to 1")

			if self.globalVarsObj.driveCapacityInGB == 256:
				if AttributeDict['EnduranceEstimate'] != 512000:
					raise ValidationError.TestFailError("FB", "FB Log Page Attribute Endurance Estimate for 256GB device is not set to 512000")

			elif self.globalVarsObj.driveCapacityInGB == 512:
				if AttributeDict['EnduranceEstimate'] != 1024000:
					raise ValidationError.TestFailError("FB", "FB Log Page Attribute Endurance Estimate for 512GB device is not set to 1024000")

			if AttributeDict['LogPageVersion'] != 3:
				raise ValidationError.TestFailError("FB", "FB Log Page Attribute LogPageVersion is not set to 3")

		#Facebook Log page parsing Structure
		#------------------------------------------------------------------------------------------------------------
		if pageID == Constants.SMART_PAGE_ID_HP:

			AttributeDict['Available_Spare'] =  self.ccmObj.GetNBytesToInt(buffer_parsed,3,1)
			AttributeDict['Percentage_Used'] =  self.ccmObj.GetNBytesToInt(buffer_parsed,5,1)
			AttributeDict['NVMI']            =  self.ccmObj.GetNBytesToInt(buffer_parsed,160,3)
			AttributeDict['IDPA']            =  self.ccmObj.GetNBytesToInt(buffer_parsed,163,3)
			AttributeDict['LBAT']            =  self.ccmObj.GetNBytesToInt(buffer_parsed,166,2)
			AttributeDict['CRCC']            =  self.ccmObj.GetNBytesToInt(buffer_parsed,168,4)
			AttributeDict['UECC']            =  self.ccmObj.GetNBytesToInt(buffer_parsed,172,4)

		if pageID == Constants.SMART_PAGE_ID_MSFT_C0:

			AttributeDict['PhysicalMediaUnitsWritten']       =  self.ccmObj.GetNBytesToInt(buffer_parsed,0,16)
			AttributeDict['PhysicalMediaUnitsRead']          =  self.ccmObj.GetNBytesToInt(buffer_parsed,16,16)
			AttributeDict['BadUserNANDBlock_Raw']            =  self.ccmObj.GetNBytesToInt(buffer_parsed,32,6)
			AttributeDict['BadUserNANDBlock_Normalized']     =  self.ccmObj.GetNBytesToInt(buffer_parsed,38,2)
			AttributeDict['BadSystemNANDBlock_Raw']          =  self.ccmObj.GetNBytesToInt(buffer_parsed,40,6)
			AttributeDict['BadSystemNANDBlock_Normalized']   =  self.ccmObj.GetNBytesToInt(buffer_parsed,46,2)
			AttributeDict['XORRecoverycount']                =  self.ccmObj.GetNBytesToInt(buffer_parsed,48,8)
			AttributeDict['UncorrectableReadErrorCount']     =  self.ccmObj.GetNBytesToInt(buffer_parsed,56,8)
			AttributeDict['SoftECCerrorcount']               =  self.ccmObj.GetNBytesToInt(buffer_parsed,64,8)
			AttributeDict['SSDE2E_DetectedErrors']           =  self.ccmObj.GetNBytesToInt(buffer_parsed,72,4)
			AttributeDict['SSDE2E_CorrectedErrors']          =  self.ccmObj.GetNBytesToInt(buffer_parsed,76,4)
			AttributeDict['SystemData_%ageUsed']             =  self.ccmObj.GetNBytesToInt(buffer_parsed,80,1)
			AttributeDict['Refreshcount']                    =  self.ccmObj.GetNBytesToInt(buffer_parsed,81,7)
			AttributeDict['MaxPEC']                          =  self.ccmObj.GetNBytesToInt(buffer_parsed,88,4)
			AttributeDict['MinPEC']                          =  self.ccmObj.GetNBytesToInt(buffer_parsed,92,4)
			AttributeDict['TT_Count']                        =  self.ccmObj.GetNBytesToInt(buffer_parsed,96,1)
			AttributeDict['TT_Status']                       =  self.ccmObj.GetNBytesToInt(buffer_parsed,97,1)
			AttributeDict['OCPNVMe_Spec_ErrataVersion']      =  self.ccmObj.GetNBytesToInt(buffer_parsed,98,1)
			AttributeDict['OCPNVMe_Spec_PointVersion']       =  self.ccmObj.GetNBytesToInt(buffer_parsed,99,2)
			AttributeDict['OCPNVMe_Spec_MinorVersion']       =  self.ccmObj.GetNBytesToInt(buffer_parsed,101,2)
			AttributeDict['OCPNVMe_Spec_MajorVersion']       =  self.ccmObj.GetNBytesToInt(buffer_parsed,103,1)
			AttributeDict['PCIeCorrectableErrorcount']       =  self.ccmObj.GetNBytesToInt(buffer_parsed,104,8)
			AttributeDict['IncompleteShutdowns']             =  self.ccmObj.GetNBytesToInt(buffer_parsed,112,4)
			AttributeDict['Reserved1']                       =  self.ccmObj.GetNBytesToInt(buffer_parsed,116,4)
			AttributeDict['%FreeBlocks_User']                =  self.ccmObj.GetNBytesToInt(buffer_parsed,120,1)
			AttributeDict['Reserved2']                       =  self.ccmObj.GetNBytesToInt(buffer_parsed,121,7)
			AttributeDict['CapacitorHealth']                 =  self.ccmObj.GetNBytesToInt(buffer_parsed,128,2)
			AttributeDict['NVMeErrataVersion']               =  self.ccmObj.GetNBytesToInt(buffer_parsed,130,1)
			AttributeDict['Reserved3']                       =  self.ccmObj.GetNBytesToInt(buffer_parsed,131,5)
			AttributeDict['Unaligned_IO']                    =  self.ccmObj.GetNBytesToInt(buffer_parsed,136,8)
			AttributeDict['SecurityVersionNumber']           =  self.ccmObj.GetNBytesToInt(buffer_parsed,144,8)
			AttributeDict['NUSE']                            =  self.ccmObj.GetNBytesToInt(buffer_parsed,152,8)
			AttributeDict['PLPStartCount']                   =  self.ccmObj.GetNBytesToInt(buffer_parsed,160,16)
			AttributeDict['EnduranceEstimate']               =  self.ccmObj.GetNBytesToInt(buffer_parsed,176,16)
			AttributeDict['PCIeLinkRe-trainingCount']        =  self.ccmObj.GetNBytesToInt(buffer_parsed,192,8)
			AttributeDict['Reserved4']                       =  self.ccmObj.GetNBytesToInt(buffer_parsed,200,294)
			AttributeDict['LogPageVersion']                  =  self.ccmObj.GetNBytesToInt(buffer_parsed,494,2)
			AttributeDict['LogPageGUID']                     =  self.ccmObj.GetNBytesToInt(buffer_parsed,496,16)

			if AttributeDict['LogPageVersion'] != 3:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute LogPageVersion is not set to 3")

			if AttributeDict['LogPageGUID'] != 233721280104791642383937574454470684613L:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute LogPageGUID is not set to 233721280104791642383937574454470684613L")

			if AttributeDict['CapacitorHealth'] != 65535:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute CapacitorHealth is not set to 65535")

			if AttributeDict['NVMeErrataVersion'] != 99:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute NVMeErrataVersion is not set to 99")

			if AttributeDict['PLPStartCount'] != 0:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute PLPStartCount is not set to 0")

			if AttributeDict['OCPNVMe_Spec_MajorVersion'] != 2:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute OCPNVMe_Spec_MajorVersion is not set to 2")

			if AttributeDict['OCPNVMe_Spec_ErrataVersion'] != 0:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute OCPNVMe_Spec_ErrataVersion is not set to 0")

			if AttributeDict['OCPNVMe_Spec_PointVersion'] != 0:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute OCPNVMe_Spec_PointVersion is not set to 0")

			if AttributeDict['OCPNVMe_Spec_MinorVersion'] != 0:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute OCPNVMe_Spec_MinorVersion is not set to 0")

			if AttributeDict['SecurityVersionNumber'] != 0:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute SecurityVersionNumber is not set to 0")

			if AttributeDict['Unaligned_IO'] != 0:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute Unaligned_IO is not set to 0")

			#self.EnduranceEstimate = self.elpObj.getEnduranceLogPageAttributes(attribute='EnduranceEstimate')

			#if AttributeDict['EnduranceEstimate'] != self.EnduranceEstimate:
				#raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute EnduranceEstimate is not equal to EE of endurance log page")

			identifyNamespacesObj = self.ccmObj.IdentifyNamespaces(0x1,pyWrap.SEND_IMMEDIATE)
			self.NUSE = identifyNamespacesObj.NUSE

			if AttributeDict['NUSE'] != self.NUSE:
				raise ValidationError.TestFailError("MS_C0", "MS_C0 Log Page Attribute NUSE is not equal to IdentifyNamespace-NUSE")

		if pageID == Constants.SMART_PAGE_ID_DELL:
			return self.parseDellLogPage(buffer_parsed, pageID)

		return AttributeDict

	def parseDellLogPage(self, smartBuffer, pageID):
		"""Function which handles parsing of Dell log page 0xCA. Will return class object"""

		#if Dell spec is AO05 or lower then we can call VendorSMARTWrapper (leveraged code)
		if self.globalVarsObj.GenericFWStructure.Morpheous_map['GLP']['DellSpecVersion'] in ['A04', 'A05']:
			#using the old method (VTF vendorSmartWrapper) for time being, untill we come up with better log page design framework which will be handled within FVT only
			smartObj = SmartWrap.CreateSMARTFromBuffer(smartBuffer, pageID)
		else:
			smartObj = ParseDellLog()
			for i in smartObj.dellAttributes.keys():
				setattr(smartObj, i, self.utilsObj.ReturnIntFromBuffer(smartBuffer, smartObj.dellAttributes[i][0], smartObj.dellAttributes[i][1]))

		return smartObj

	def PerformAttributeIntegrityCheck(self):

	#-----------------------------------------------------------------------------------------------------------------------------------------
		# Detect FW Version and If EI Build remove FFU from Event List
		FW_Version = self.globalVarsObj.vtfContainer.execution_info.testDataCollection['IDD fw Revision']

		attributeList = []
		Exceptional_List = []
		Exceptional_List1 = []

		#SMART Attribue Lists
		SMART_Attribute = ["AvailableSpare", "AvailableSpareThrsld", "PercentageUsed", "DataUnitsRead", "DataUnitsWritten", "HostReadCommands", "HostWriteCommands", "PowerOnHours", "MediaDataIntegrity", "NumberOfErrorsLogged", "CriticalWarning", "ControllerBusyTime"]
		#attributeList.append(SMART_Attribute)
		attributeList = SMART_Attribute
		if self.isFB:
			Exceptional_List = ["PhysicalMediaUnitsWrittenTLC","PhysicalMediaUnitsWrittenSLC","PhysicalMediaUnitsRead","%FreeBlocks_User","BackgroundBack-PressureGauge"]
			FB_Attribute_Dict = self.GetSmartLogObj(Constants.SMART_PAGE_ID_FB)
			FB_Attribute = FB_Attribute_Dict.keys()
			for ele in Exceptional_List:
				if ele in FB_Attribute:
					FB_Attribute.remove(ele)
			self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "FB_AttributeList = {0}".format(FB_Attribute))
			attributeList.extend(FB_Attribute)


		if FW_Version[-1] != "E":
			#HERMII-7646 FFU Rollback issue
			Before_FFU = {}
			self.EOLPECSLC_Initial , self.EOLPECTLC_Initial = self.Read_PEC_Threshold()

			for parameters in attributeList:
				if self.isFB:
					if parameters in FB_Attribute:
						Before_FFU[parameters] = self.GetSmartLogObj(Constants.SMART_PAGE_ID_FB)[parameters]
					else:
						Before_FFU[parameters] = self.GetSMARTAttribute(Constants.SMART_PAGE_ID_GENERIC, parameters)
				else:
					Before_FFU[parameters] = self.GetSMARTAttribute(Constants.SMART_PAGE_ID_GENERIC, parameters)


			#FFU download and Commit code
			self.ffuUtilsObj.firmwaredownloadfrombuffer()
			self.ffuUtilsObj.firmwarecommit(self.firmwareSlot, 1)

			self.ccmObj.Delay(2)

			self.ccmObj.NvmeControllerReset(IsAsync=True,sendType=pyWrap.SEND_IMMEDIATE)
			self.ccmObj.Delay(1)
			self.ccmObj.NVMeControllerActivate(bytDisableDone=True)

			self.EOLPECSLC_Final , self.EOLPECTLC_Final = self.Read_PEC_Threshold()

			if (self.EOLPECSLC_Initial != self.EOLPECSLC_Final) or (self.EOLPECTLC_Initial!= self.EOLPECTLC_Initial):
				raise ValidationError.TestFailError("FFU Check", "PEC is not same after FFU")

			After_FFU = {}

			for parameters in attributeList:

				if self.isFB:
					if parameters in FB_Attribute:
						After_FFU[parameters] = self.GetSmartLogObj(Constants.SMART_PAGE_ID_FB)[parameters]
					else:
						After_FFU[parameters] = self.GetSMARTAttribute(Constants.SMART_PAGE_ID_GENERIC, parameters)
				else:
					After_FFU[parameters] = self.GetSMARTAttribute(Constants.SMART_PAGE_ID_GENERIC, parameters)


			for parameters in attributeList:
				self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"| Log Page Attribute {0:^25} | Before FFU = {1:^10} | After FFU = {2:^10} |".format(parameters, Before_FFU[parameters], After_FFU[parameters]))

			#---------------------------------------------------------------------------------------------------------------------------------------------------
			# Check Both Dictionary Should be equal after FFU
			for parameters in attributeList:
				if After_FFU[parameters] != Before_FFU[parameters]:
					raise ValidationError.TestFailError("Attribute Integrity Check", "Log Page Attribute {0} Value changed after FFU".format(parameters))


		#-----------------------------------------------------------------------------------------------------------------------------------------


		#-----------------------------------------------------------------------------------------------------------------------------------------
		# Issue GSD to Perform Control Sync before performing Attribute Integrity Check
		self.ccmObj.GSD()

		#-----------------------------------------------------------------------------------------------------------------------------------------
		# Events to be issued
		Event_List = ['GSD', "UGSD", "PA", "CTRLRESET", "FLRRESET", "LINKRESET", "HOTRESET", "PERST", "GetLogPage", "FFU", "Format", "Sanitize"]
		if self.ccmObj.ControllerCapability().NSSRS:
			Event_List.append("SSRESET")

		# Issuing Link Reset only if syncMode is set to true in command line
		if self.vtfContainer.cmd_line_args.syncMode == False:
			Event_List.remove('LINKRESET')

		# Detect FW Version and If EI Build remove FFU from Event List
		if FW_Version[-1] == "E":
			Event_List.remove("FFU")

		self.MediaRo = self.GetSmartLogObj(Constants.SMART_PAGE_ID_GENERIC)
		if (self.MediaRo.CriticalWarning & 0x8):
			Event_List.remove("Format")
			Event_List.remove("Sanitize")

		#Shuffling the list to have random sequence of event in every test
		self.globalVarsObj.randomObj.shuffle(Event_List)
		self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "Shuffled List = {0}".format(Event_List))

		#----------------------------------------------------------------------------------------------------------------------------------------
		# Issue All the event type from event list in for loop and check for attribute Persistency

		for event in Event_List:
			self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "The selected event from the Event_List is {0}".format(event))

			#-----------------------------------------------------------------------------------------------------------------------------------------
			#Creating a Dictionary and storing Attribute values before Reset
			Before_Reset = {}

			for attribute in attributeList:
				self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "The selected attribute is  {0}".format(attribute))
				if self.isFB:
					if attribute in FB_Attribute:
						Before_Reset[attribute] = self.GetSmartLogObj(Constants.SMART_PAGE_ID_FB)[attribute]
					else:
						Before_Reset[attribute] = self.GetSMARTAttribute(Constants.SMART_PAGE_ID_GENERIC, attribute)

				else:
					Before_Reset[attribute] = self.GetSMARTAttribute(Constants.SMART_PAGE_ID_GENERIC, attribute)




			if(event.upper() == "GSD"):
				self.ccmObj.GSD()

			elif(event.upper() == "UGSD"):
				self.ccmObj.Delay(601)
				self.ccmObj.UGSD()

			elif(event.upper() == "ABORT"):
				self.ccmObj.Delay(601)
				self.ccmObj.PowerAbort()

			elif(event.upper() == "CTRLRESET"):
				self.ccmObj.NvmeControllerReset(IsAsync=True,sendType=pyWrap.SEND_IMMEDIATE)
				self.ccmObj.Delay(1)
				self.ccmObj.NVMeControllerActivate(bytDisableDone=True)

			elif(event.upper() == "SSRESET"):
				self.ccmObj.NvmeSubsystemReset(IsAsync=True, sendType = pyWrap.SEND_IMMEDIATE)
				self.ccmObj.Delay(5)
				self.ccmObj.NVMeControllerActivate(bytNvmSubsystemResetDone=True)

			elif(event.upper() == "FLRRESET"):
				self.ccmObj.Delay(601)
				self.ccmObj.PcieFunctionalLevelResetEnter(AsyncMode=True,sendType=pyWrap.SEND_IMMEDIATE)
				self.ccmObj.Delay(1)
				self.ccmObj.PcieFunctionalLevelResetExit()

			elif(event.upper() == "LINKRESET"):
				self.ccmObj.PcieLinkResetEnter(AsyncMode=False)
				self.ccmObj.Delay(5)
				self.ccmObj.PcieLinkResetExit()

			elif(event.upper() == "HOTRESET"):
				self.ccmObj.PcieHotResetEnterAndExit(isAsync=True,sendType=pyWrap.SEND_IMMEDIATE)

			elif(event.upper() == "PERST"):
				self.ccmObj.Delay(601)
				self.ccmObj.DoFlushCache()
				pyWrap.PERSTReset(assertTime=5000, isAsync=False, sendType=pyWrap.SEND_IMMEDIATE)
				self.globalVarsObj.ccmObj.Delay(secondsToSleep = 2)
				self.globalVarsObj.HMBAfterPowerCycle = 0

			elif event == "GetLogPage":
				for _ in range(1000):
					self.GetSmartLogObj(Constants.SMART_PAGE_ID_GENERIC)

			elif event == "FFU":
				#FFU download and Commit code
				self.ffuUtilsObj.firmwaredownloadfrombuffer()
				self.ccmObj.GetFWSlotInfo(0)
				if self.commitAction == 2:
					self.firmwareSlot = 1 if self.globalVarsObj.ActiveFirmwareSlot == 2 else 2
					self.ffuUtilsObj.firmwarecommit(self.firmwareSlot, 0)
					self.ffuUtilsObj.firmwarecommit(self.firmwareSlot, 2)
				elif self.commitAction == 3:
					if self.isHP:
						self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"Changing to CA1 as HP doesnot support CA3 for SMART")
						self.ffuUtilsObj.firmwarecommit(self.firmwareSlot, 1)

				else:
					self.ffuUtilsObj.firmwarecommit(self.firmwareSlot, self.commitAction)
				#including this to activate the Firmware
				self.ccmObj.GSD()

			elif event == "Format" or event == "Sanitize":
				Exceptional_List1 = ["PercentageUsed"]
				if event == "Format":
					self.ccmObj.Format(SES = 1, isAsync=False)
				else :
					import SanitizeUtils
					from Constants import SANITIZE_CONSTANTS as saniCons
					self.sanitizeutilsobj=SanitizeUtils.SanitizeUtils(self.logger, self.vtfContainer, verifyCapability=False)
					self.ccmObj.Sanitize()
					self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "Check for sanitize completion(sanitize log page)")
					sanitizeLogObj = self.sanitizeutilsobj.GetSanitizeLogObj()
					while (sanitizeLogObj.SPROG != saniCons.SPROGDeafultStatus):
						self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "SanitizeOnProgress: , SPROG = {0}%, Sanitize Status = {1}".format((sanitizeLogObj.SPROG*100/saniCons.SPROGconst), sanitizeLogObj.lastSanitizeStatus))
						sanitizeLogObj = self.sanitizeutilsobj.GetSanitizeLogObj()
					self.globalVarsObj.logger.Info(self.globalVarsObj.TAG, "Verify Sanitize completion")
					SanitizeExpectedStatus = 1
					sanitizeLogObj = self.sanitizeutilsobj.GetSanitizeLogObj()
					if sanitizeLogObj.lastSanitizeStatus != SanitizeExpectedStatus:
						raise ValidationError.TestFailError("VerifyLogAfterSanitize", "Sanitize status = {0}, expected status = {1}".format(sanitizeLogObj.lastSanitizeStatus, SanitizeExpectedStatus))

			#--------------------------------------------------------------------------------------------------------------------------------------------------
			#Creating a Dictionary and storing Attribute values After Reset

			After_Reset = {}

			for attribute in attributeList:

				if self.isFB:
					if attribute in FB_Attribute:
						After_Reset[attribute] = self.GetSmartLogObj(Constants.SMART_PAGE_ID_FB)[attribute]
					else:
						After_Reset[attribute] = self.GetSMARTAttribute(Constants.SMART_PAGE_ID_GENERIC, attribute)
				else:
					After_Reset[attribute] = self.GetSMARTAttribute(Constants.SMART_PAGE_ID_GENERIC, attribute)


			for attribute in attributeList:

				self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"| Log Page Attribute {0:^25} | Before {3} = {1:^10} | After {3} = {2:^10} |".format(attribute, Before_Reset[attribute], After_Reset[attribute],event))


			#---------------------------------------------------------------------------------------------------------------------------------------------------
			# Check Both Dictionary Should be equal
			for attribute in attributeList:
				if attribute == "PowerOnHours":

					if After_Reset[attribute] - Before_Reset[attribute] > 1:

						raise ValidationError.TestFailError("Attribute Integrity Check", "Log Page Attribute {0} Value changed after {1}".format(attribute, event))

				elif attribute == "AvailableSpare":

					if (After_Reset[attribute] == 0 and Before_Reset[attribute]==4) or (After_Reset[attribute] == Before_Reset[attribute]):

						pass

					else:

						raise ValidationError.TestFailError("Attribute Integrity Check", "Log Page Attribute {0} Value changed after {1}".format(attribute, event))

				elif attribute == "ControllerBusyTime":

					if (After_Reset["PowerOnHours"]!= 0) :
						After_Reset["PowerOnHours"] = (After_Reset["PowerOnHours"] *  60)
						if After_Reset["PowerOnHours"] > After_Reset[attribute]:
							self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"POH is greater than controllerbusy time")
						else:
							raise ValidationError.TestFailError("Attribute Integrity Check","Controller busy time is greater")

				elif (After_Reset[attribute] != Before_Reset[attribute]):

					if (attribute in Exceptional_List) or (attribute in Exceptional_List1):
						self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"Attribute Integrity Check", "Log Page Attribute {0} Value changed after {1}".format(attribute, event))

					elif ((attribute == "MaxPECSLC") or (attribute == "MaxPECTLC") or (attribute == "MinPECSLC") or (attribute == "MinPECTLC")) and (Before_Reset[attribute]+1 == After_Reset[attribute]):
						self.globalVarsObj.logger.Info(self.globalVarsObj.TAG,"Attribute Integrity Check", "Log Page Attribute {0} Value changed after {1}".format(attribute, event))

					else:
						raise ValidationError.TestFailError("Attribute Integrity Check", "Log Page Attribute {0} Value changed after {1}".format(attribute, event))


		self.MediaRo = self.GetSmartLogObj(Constants.SMART_PAGE_ID_GENERIC)
		if (self.MediaRo.CriticalWarning & 0x8):
			self.vtfContainer.DoProduction()
			self.globalVarsObj.Production_Done = True
			self.globalVarsObj.HMBAfterPowerCycle = 0