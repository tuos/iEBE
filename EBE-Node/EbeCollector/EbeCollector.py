#!/usr/bin/env python2
"""
    This module consists of functions dealing with the collection event-by-event
    results into databases.

"""

from os import path, listdir
import re
from DBR import SqliteDB
from assignmentFormat import assignmentExprStream2IndexDict

class EbeCollector:
    """
        This class contains functions that collect results from event-by-event
        calculations into databases.
    """

    def collectEccentricitiesAndRIntegrals(self, folder, event_id, db, oldStyleStorage=False):
        """
            This function collects initial eccentricities and r-integrals into
            the specified SqliteDB object "db". More specifically,
            this functions fills table "ecc_id_lookup", "eccentricity", and
            "r_integrals".

            Eccentricity and r-integral files will be looked for in "folder" and
            when filling tables the specified "event_id" will be used.

            When "oldStyleStorage" is set to True, another subfolder
            with name "results" will be appended to "folder" which will
            be compatible to the old style storage format.
        """
        # compatibility treatment
        if oldStyleStorage: folder = path.join(folder, "results")
        # collection of file name patterns, ecc_id, and ecc_type_name
        typeCollections = (
            (
                re.compile("ecc-init-sd-r_power-(\d*).dat"), # filename pattern
                1, # ecc_id
                "sd", # ecc_type_name
            ),
            (
                re.compile("ecc-init-r_power-(\d*).dat"),
                2,
                "ed",
            )
        )
        # they have the following formats (column indices)
        ecc_real_col = 0 # real part of ecc
        ecc_imag_col = 1 # imag part of ecc
        r_inte_col = 3 # r-integral

        # first write the ecc_id_lookup table, makes sure there is only one such table
        if db.createTableIfNotExists("ecc_id_lookup", (("ecc_id","integer"), ("ecc_type_name","text"))):
            for pattern, ecc_id, ecc_type_name in typeCollections:
                db.insertIntoTable("ecc_id_lookup", (ecc_id, ecc_type_name))

        # next create the eccentricity and r_integrals table, if not existing
        db.createTableIfNotExists("eccentricity", (("event_id","integer"), ("ecc_id", "integer"), ("r_power", "integer"), ("n","integer"), ("ecc_real","real"), ("ecc_imag","real")))
        db.createTableIfNotExists("r_integrals", (("event_id","integer"), ("ecc_id","integer"), ("r_power","integer"), ("r_inte","real")))

        # the big loop
        for aFile in listdir(folder): # get all file names
            for pattern, ecc_id, ecc_type_name in typeCollections: # loop over ecc types
                matchResult = pattern.match(aFile) # try to match file names
                if not matchResult: continue # not matched!
                filename = matchResult.group()
                r_power = matchResult.groups()[0] # indicated by the file name
                # read the eccentricity file and write database
                for n, aLine in enumerate(open(path.join(folder, filename))): # row index is "n"
                    data = aLine.split()
                    # insert into eccentricity table
                    db.insertIntoTable("eccentricity",
                                        (event_id, ecc_id, r_power, n, float(data[ecc_real_col]), float(data[ecc_imag_col]))
                                    )
                    # insert into r-integrals table but only once
                    if n==1:
                        db.insertIntoTable("r_integrals",
                                            (event_id, ecc_id, r_power, float(data[r_inte_col]))
                                        )

        # close connection to commit changes
        db.closeConnection()


    def collectFLowsAndMultiplicities_urqmdBinUtilityFormat(self, folder, event_id, db, multiplicityFactor=1.0):
        """
            This function collects integrated and differential flows data
            and multiplicity and spectra data from "folder" into the
            database "db" using event id "event_id". The "multiplityFactor"
            will be multiplied to the number of particles read from file to
            form the multiplicity value.

            This function fills the following table: "pid_lookup",
            "inte_vn", "diff_vn", "multiplicities", "spectra".

            This funtion should only be applied to a folder where flow
            files are generated by the binUtilities module specifically
            for urqmd.
        """
        # collection of file name patterns, pid, and particle name. The file format is determined from the "filename_format.dat" file
        pidDict = {
            "Charged"       : 0, # particle name, pid
            "Pion"          : 211,
            "Kaon"          : 321,
            "Proton"        : 2212,
        }
        filePattern = re.compile("([a-zA-z]*)_flow_([a-zA-Z+]*).dat") # filename pattern, the 2nd matched string needs to be among the pidTable above in order to be considered "matched"; the 1st matched string will either be "integrated" or "differential"
        tableChooser = { # will be used to decide which table to write to
            "integrated"    :   ("inte_vn", "multiplicities"),
            "differential"  :   ("diff_vn", "spectra"),
        }

        # next read in file format, which is assumed to be stored in the file "integrated_flow_format.dat" and "differential_flow_format.dat" (same)
        fmt = assignmentExprStream2IndexDict(open(path.join(folder, "integrated_flow_format.dat"))) # column index will automatically be 0-based
        N_col = fmt["count"] # number of particles for the given condition (diff or inte)
        pT_col = fmt["pT_mean_real"]
        vn_real_cols = {} # will have items (n, column index)
        vn_imag_cols = {}
        # probe for the largest n value
        largest_n = 1
        allFields = fmt.keys()
        while ("v_%d_mean_real" % largest_n) in allFields:
            vn_real_cols[largest_n] = fmt["v_%d_mean_real" % largest_n]
            vn_imag_cols[largest_n] = fmt["v_%d_mean_imag" % largest_n]
            largest_n += 1

        # first write the pid_lookup table, makes sure there is only one such table
        if db.createTableIfNotExists("pid_lookup", (("name","text"), ("pid","integer"))):
            db.insertIntoTable("pid_lookup", list(pidDict.items()))

        # next create various tables
        db.createTableIfNotExists("inte_vn", (("event_id","integer"), ("pid","integer"), ("pT","real"), ("n","integer"), ("vn_real","real"), ("vn_imag","real")))
        db.createTableIfNotExists("diff_vn", (("event_id","integer"), ("pid","integer"), ("pT","real"), ("n","integer"), ("vn_real","real"), ("vn_imag","real")))
        db.createTableIfNotExists("multiplicities", (("event_id","integer"), ("pid","integer"), ("pT","real"), ("N","real")))
        db.createTableIfNotExists("spectra", (("event_id","integer"), ("pid","integer"), ("pT","real"), ("N","real")))

        # the big loop
        for aFile in listdir(folder): # get all file names
            matchResult = filePattern.match(aFile) # try to match file names
            if not matchResult: continue # not matched!
            flow_type, particle_name = matchResult.groups() # indicated by the file name
            if particle_name not in pidDict.keys(): continue # dont know about this particle
            pid = pidDict[particle_name] # get pid
            filename = matchResult.group() # get the file to be opened
            flow_table, multiplicity_table = tableChooser[flow_type] # choose tables to write to
            # read the flow file and write results
            for aLine in open(path.join(folder, filename)):
                data = aLine.split()
                # write flow table
                for n in range(1, largest_n):
                    db.insertIntoTable(flow_table,
                                        (event_id, pid, float(data[pT_col]), n, float(data[vn_real_cols[n]]), float(data[vn_imag_cols[n]]))
                                    )
                # write multiplicity table
                db.insertIntoTable(multiplicity_table,
                                        (event_id, pid, float(data[pT_col]), float(data[N_col])*multiplicityFactor)
                                    )

        # close connection to commit changes
        db.closeConnection()


    def collectFLowsAndMultiplicities_iSFormat(self, folder, event_id, db):
        """
            This function collects integrated and differential flows data
            and multiplicity and spectra data from "folder" into the
            database "db" using event id "event_id".

            This function fills the following table: "pid_lookup",
            "inte_vn", "diff_vn", "multiplicities", "spectra".

            This funtion should only be applied to a folder where flow
            files are generated by the iS (or iSS with calculate flow
            mode) module as in pure hydro calculations. As such, the
            subfolder name "spectra" will be appended to "folder"
            automatically.
        """
        pass


    def createDatabaseFromEventFolders(self, folder, subfolderPattern="event-(\d*)", databaseFilename="CollectedResults.db", collectMode="fromUrQMD", multiplicityFactor=1.0):
        """
            This function collect all results (ecc+flow) from subfolders
            whose name have pattern "subfolderPattern" to a database
            with name "databaseFilename".

            The "subfolderPattern" argument can be such that when it
            matches, if its groups()[0] exists, it will be used as event
            id, otherwise the order of the subfolder in listdir will be
            used as event id. Only folders will be matched in either
            case.

            The "collectMode" argument controls how data files to be
            collected are stored internally, and whether oversampling is
            enabled. So far it can be set to either "fromUrQMD" or
            "fromPureHydro":

            -- "fromUrQMD": For eccentricity it will set
            "oldStyleStorage=False" in the
            collectEccentricitiesAndRIntegrals function; for flows
            collectFLowsAndMultiplicities_urqmdBinUtilityFormat will be
            called. In this mode "multiplicityFactor" will be passed
            along to collectFLowsAndMultiplicities_urqmdBinUtilityFormat
            function.

            -- "fromPureHydro": For eccentricity it will set
            "oldStyleStorage=True" in the
            collectEccentricitiesAndRIntegrals function; for flows
            collectFLowsAndMultiplicities_iSFormat will be called.
        """
        # get list of (matched subfolders, event id)
        matchPattern = re.compile(subfolderPattern)
        matchedSubfolders = []
        for folder_index, aSubfolder in enumerate(listdir(folder)):
            fullPath = path.join(folder, aSubfolder)
            if not path.isdir(fullPath): continue # want only folders, not files
            matchResult = matchPattern.match(aSubfolder)
            if matchResult: # matched!
                if len(matchResult.groups()): # folder name contains id
                    event_id = matchResult.groups()[0]
                else:
                    event_id = folder_index
                matchedSubfolders.append((fullPath, event_id)) # matched!

        # the data collection loop
        db = SqliteDB(path.join(folder, databaseFilename))
        if collectMode == "fromUrQMD":
            for aSubfolder, event_id in matchedSubfolders:
                self.collectEccentricitiesAndRIntegrals(aSubfolder, event_id, db) # collect ecc
                self.collectFLowsAndMultiplicities_urqmdBinUtilityFormat(aSubfolder, event_id, db, multiplicityFactor) # collect flow
        elif collectMode == "fromPureHydro":
            for aSubfolder, event_id in matchedSubfolders:
                self.collectEccentricitiesAndRIntegrals(aSubfolder, event_id, db, oldStyleStorage=True) # collect ecc
                self.collectFLowsAndMultiplicities_iSFormat(aSubfolder, event_id, db) # collect flow


    def mergeDatabases(self, toDB, fromDB):
        """
            Meger the database "fromDB" to "toDB"; both are assumed to be
            databases created from ebe calculations, meaning that they only
            contain tables specified in EbeCollector_readme.
        """
        for aTable in fromDB.getAllTableNames():
            # first copy table structure
            firstCreation = toDB.createTableIfNotExists(aTable, fromDB.getTableInfo(aTable))
            if firstCreation:
                # just copy
                toDB.insertIntoTable(aTable, fromDB.selectFromTable(aTable))
            else: # treatment depends on table type
                if "lookup" in aTable: continue # if it's a lookup table, nothing to be done
                # not a lookup table: shift up event_id by the current existing max
                currentEventIdMax = toDB.selectFromTable(aTable, "max(event_id)")[0][0]
                def shiftEID(row):
                    newRow = list(row)
                    newRow[0] += currentEventIdMax
                    return newRow
                toDB.insertIntoTable(aTable, list(map(shiftEID, fromDB.selectFromTable(aTable))))
        toDB.closeConnection() # commit


if __name__ == '__main__':
    import doctest
    doctest.testfile("EbeCollector_readme.txt")
