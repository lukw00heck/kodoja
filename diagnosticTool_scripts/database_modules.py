"""Database construction modules."""
import subprocess
import pandas as pd
import os
import urllib
import re


# Download refseq files from ncbi ftp site - use ncbi-genome-download
def ncbi_download(tool, genome_download_dir, parallel, host, test):
    """Download genomic or protein data from NCBI ftp site using ncbi-genome-download."""
    assert (tool == "kraken") | (tool == "kaiju"),\
        "Argument 'tool' must be either 'kraken' or 'kaiju'."
    if tool == "kraken":
        file_format = "fasta"
    else:
        file_format = "protein-fasta"

    # Check directory exists
    if not os.path.exists(genome_download_dir):
        os.makedirs(genome_download_dir)

    ngd_command = "ncbi-genome-download -F " + file_format + " -o " + genome_download_dir
    if test:
        for taxid in test:
            taxid_ngd_command = ngd_command + " --species-taxid " + str(taxid) + " viral"
            subprocess.check_call(taxid_ngd_command, shell=True)
    else:
        if host:
            for taxid in host:
                taxid_ngd_command = ngd_command + " --species-taxid " + str(taxid) + " plant"
                subprocess.check_call(taxid_ngd_command, shell=True)

        ngd_command += " --parallel " + str(parallel) + " viral"
        subprocess.check_call(ngd_command, shell=True)


def ncbi_rename_customDB(tool, genome_download_dir, extra_files=False, extra_taxid=False):
    """Rename ncbi data files for custom databases.

    To add NCBI files to database Kraken and Kaiju require the files to have formatted
    identifiers. This script modifies identifiers of files ending in .fna to kraken
    format, and files ending in .faa to kaiju format. Once renamed, original files are
    deleted.

    """
    assert (tool == "kraken") | (tool == "kaiju"), "Argument 'tool' must be either 'kraken' or 'kaiju'."
    if tool == "kraken":
        file_extension = ".fna.gz"
    else:
        file_extension = ".faa.gz"

    path_assembly_summary = genome_download_dir + "viral_assembly_summary.txt"
    assembly_summary = pd.read_table(path_assembly_summary, sep='\t',
                                     skiprows=1, header=0)
    assembly_summary.rename(columns={'# assembly_accession': 'assembly_accession'},
                            inplace=True)  # rename column to exclude "#"

    kaiju_count = 1  # Count for protein sequences
    for root, subdirs, files in os.walk(genome_download_dir):
        for filename in files:
            if filename.endswith(file_extension) and not filename.endswith(tool + file_extension):
                zip_filename = os.path.join(root, filename)
                subprocess.check_call("gunzip " + zip_filename, shell=True)  # Uncompress ".gz" file
                unzip_filename = zip_filename[:-3]

                if root.endswith("extra"):
                    id_loc = [i for i, x in enumerate(extra_files) if x == filename][0]
                    assert 'id_loc' in locals() or 'id_loc' in globals(),\
                        "Error: problem with name of the extra files provided"
                    taxid = extra_taxid[id_loc]
                    assert 'taxid' in locals() or 'taxid' in globals(),\
                        "Error: problem with the taxid of the extra files provided"
                else:
                    # Retrieve assembly accession number for file path
                    assembly_accession = re.findall(r'/viral/([^(]*)/', unzip_filename)
                    assert 'assembly_accession' in locals() or 'assembly_accession' in globals(),\
                        "Can't locate assemble accession"
                    # retrieve taxid for file
                    taxid_list = list(assembly_summary.loc[assembly_summary['assembly_accession'] == assembly_accession[0]]["taxid"])
                    assert (len(taxid_list) == 1),\
                        "Taxid has " + len(taxid) + "vales. Should only have 1 value"
                    taxid = taxid_list[0]

                # Create new genomic file with rename sequence identifier to comply with tool
                #  requirements for custom database
                renamed_file = unzip_filename[:-4] + "." + tool + unzip_filename[-4:]
                with open(renamed_file, 'w') as out_file, open(unzip_filename, 'r') as in_file:
                    for line in in_file:
                        if line[0] == ">":
                            if tool == "kraken":
                                if " " in line:
                                    insert = line.index(" ")
                                else:
                                    insert = len(line) - 1
                                out_file.write(line[:insert] + "|kraken:taxid|" + str(taxid) + line[insert:])
                            else:
                                out_file.write(">" + str(kaiju_count) + "_" + str(taxid) + "\n")
                                kaiju_count += 1
                        else:
                            out_file.write(line)
                # Delete original file
                subprocess.check_call("rm " + unzip_filename, shell=True)
                # Compress modified file
                subprocess.check_call("gzip " + renamed_file, shell=True)


def krakenDB_build(genome_download_dir, kraken_db_dir, threads, kraken_kmer, kraken_minimizer,
                   subset_vir_assembly, jellyfish_hash_size=False, kraken_max_dbSize=False):
    """Build kraken database with the renamed .fna files from ncbi."""
    # Make a kraken database directory
    if not os.path.exists(kraken_db_dir):
        os.makedirs(kraken_db_dir)

    # Download taxonomy for Kraken database
    subprocess.check_call("kraken-build --download-taxonomy --threads " +
                          str(threads) + " --db " + kraken_db_dir, shell=True)

    file_list = []
    # Add files downloaded and ready for kraken ("<file>.kraken.fna") to kraken library
    for root, subdirs, files in os.walk(genome_download_dir):
        for filename in files:
            if subset_vir_assembly:
                if root.split('/')[-1] in subset_vir_assembly and filename.endswith("kraken.fna.gz"):
                    file_list.append(os.path.join(root, filename))
            else:
                if filename.endswith("kraken.fna.gz"):
                    file_list.append(os.path.join(root, filename))

    for genome_file in file_list:
        zip_filename = genome_file
        subprocess.check_call("gunzip " + zip_filename, shell=True)
        unzip_filename = zip_filename[:-3]
        subprocess.check_call("kraken-build --add-to-library " + unzip_filename +
                              " --db " + kraken_db_dir, shell=True)
        subprocess.check_call("gzip " + unzip_filename, shell=True)

    kraken_command = "kraken-build --build --threads " + str(threads) + " --db " + \
                     kraken_db_dir + " --kmer-len " + str(kraken_kmer) + \
                     " --minimizer-len " + str(kraken_minimizer)
    if kraken_max_dbSize:
        kraken_command += " --max-db-size " + str(kraken_max_dbSize)

    if jellyfish_hash_size:
        kraken_command += " --jellyfish-hash-size " + jellyfish_hash_size

    subprocess.check_call(kraken_command, shell=True)

    # Clear unnecessary files from kraken database directory
    subprocess.check_call("kraken-build --clean --db " + kraken_db_dir, shell=True)


def kaijuDB_build(genome_download_dir, kaiju_db_dir, subset_vir_assembly):
    """Build kraken database with the renamed .faa files from ncbi."""
    # Make a kaiju database directory
    if not os.path.exists(kaiju_db_dir):
        os.makedirs(kaiju_db_dir)

    # Add files downloaded and ready for kaiju ("<file>.kaiju.faa") to one fasta file
    kaijuDB_fasta = kaiju_db_dir + "kaiju_library.faa"
    count = 0
    file_list = []
    for root, subdirs, files in os.walk(genome_download_dir):
        for filename in files:
            if subset_vir_assembly:
                if root.split('/')[-1] in subset_vir_assembly and filename.endswith("kaiju.faa.gz"):
                    file_list.append(os.path.join(root, filename))
            else:
                if filename.endswith("kaiju.faa.gz"):
                    file_list.append(os.path.join(root, filename))

    with open(kaijuDB_fasta, "w") as out_file:
        for protein_file in file_list:
            zip_filename = protein_file
            subprocess.check_call("gunzip " + zip_filename, shell=True)
            unzip_filename = zip_filename[:-3]
            with open(unzip_filename, 'r') as in_file:
                for line in in_file:
                    if line[0] == ">":
                        out_file.write(line[:1] + str(count) + "_" + line[1:])
                        count += 1
                    else:
                        out_file.write(line)

            subprocess.check_call("gzip " + unzip_filename, shell=True)

    # Fetch "nodes.dmp" and "names.dmp"
    if not os.path.exists(kaiju_db_dir + "names.dmp"):
        urllib.urlretrieve('ftp://ftp.ncbi.nih.gov/pub/taxonomy/taxdump.tar.gz',
                           kaiju_db_dir + 'taxdump.tar.gz')
        subprocess.check_call("tar -xzvf " + kaiju_db_dir + "taxdump.tar.gz", shell=True)

    # Build Kaiju database
    subprocess.check_call("mkbwt -n 5 -a ACDEFGHIKLMNPQRSTVWY -o " + kaiju_db_dir +
                          "kaiju_library " + kaiju_db_dir + "kaiju_library.faa", shell=True)
    subprocess.check_call("mkfmi " + kaiju_db_dir + "kaiju_library", shell=True)
    subprocess.check_call("rm " + kaiju_db_dir + "kaiju_library.faa " + kaiju_db_dir +
                          "kaiju_library.bwt " + kaiju_db_dir + "kaiju_library.sa", shell=True)
