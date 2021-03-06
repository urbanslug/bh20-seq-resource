#!/usr/bin/env python3

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--ids-to-ignore', type=str, help='file with ids to ignore in all steps, 1 id per line', required=False)
parser.add_argument('--ids-to-consider', type=str, help='file with ids to consider in all steps, 1 id per line', required=False)
parser.add_argument('--dict-ontology', type=str, help='where is the ontology',
                    default='../dict_ontology_standardization/', required=False)

args = parser.parse_args()

import os
from dateutil.parser import parse
import xml.etree.ElementTree as ET
import json
import gzip
from datetime import datetime

import sys
sys.path.append('../')
from utils import is_integer, check_and_get_ontology_dictionaries

dir_yaml = 'yaml'

date = '2020.07.09'

min_acceptable_collection_date = datetime(2019, 12, 1)

# Query on SRA: 'txid2697049[Organism]' (https://www.ncbi.nlm.nih.gov/sra/?term=txid2697049%5BOrganism%5D)
# Query on SRA: 'txid2697049[Organism:noexp] NOT 0[Mbases ' (https://www.ncbi.nlm.nih.gov/sra/?term=txid2697049%5BOrganism:noexp%5D%20NOT%200[Mbases)
#         -> Send to -> File -> Full XML -> Create File
path_sra_metadata_xml = 'SraExperimentPackage.{}.xml.gz'.format(date)

dir_dict_ontology_standardization = args.dict_ontology
path_sra_study_accessions_txt = 'SRAStudyAccessions.{}.txt'.format(date)


accession_to_ignore_set = set()

if args.ids_to_ignore:
    if not os.path.exists(args.ids_to_ignore):
        print("\tThe '{}' file doesn't exist.".format(args.ids_to_ignore))
        sys.exit(-1)

    with open(args.ids_to_ignore) as f:
        accession_to_ignore_set.update(set([x.split('.')[0] for x in f.read().strip('\n').split('\n')]))

    print('There are {} accessions to ignore.'.format(len(accession_to_ignore_set)))


accession_to_consider_set = set()

if args.ids_to_consider:
    if not os.path.exists(args.ids_to_consider):
        print("\tThe '{}' file doesn't exist.".format(args.ids_to_consider))
        sys.exit(-1)

    with open(args.ids_to_consider) as f:
        accession_to_consider_set.update(set([x.split('.')[0] for x in f.read().strip('\n').split('\n')]))

    if len(accession_to_consider_set) > 0:
        print('There are {} accessions to consider.'.format(len(accession_to_consider_set)))


field_to_term_to_uri_dict = check_and_get_ontology_dictionaries(dir_dict_ontology_standardization)


if not os.path.exists(dir_yaml):
    os.makedirs(dir_yaml)


sra_metadata_xml_file = gzip.open(path_sra_metadata_xml, 'r')
tree = ET.parse(sra_metadata_xml_file)
sra_metadata_xml_file.close()

EXPERIMENT_PACKAGE_SET = tree.getroot()

missing_value_list = []
not_created_accession_dict = {}

run_accession_set = set()
run_accession_to_downloadble_file_url_dict = {}

num_yaml_created = 0

for i, EXPERIMENT_PACKAGE in enumerate(EXPERIMENT_PACKAGE_SET):
    #print(i, EXPERIMENT_PACKAGE)

    # A general default-empty yaml could be read from the definitive one
    info_for_yaml_dict = {
        'id': 'placeholder',
        'host': {},
        'sample': {},
        'virus': {},
        'technology': {},
        'submitter': {}
    }

    RUN_SET = EXPERIMENT_PACKAGE.find('RUN_SET')
    RUN = RUN_SET.find('RUN')
    accession = RUN.attrib['accession']

    run_accession_set.add(accession)
    #print(accession)

    if accession in accession_to_ignore_set:
        continue

    if len(accession_to_consider_set) > 0 and accession not in accession_to_consider_set:
        continue

    info_for_yaml_dict['sample']['sample_id'] = accession

    #SRAFiles = RUN.find('SRAFiles')
    #if SRAFiles is not None:
    #    url = SRAFiles.find('SRAFile').attrib['url']
    #    if 'sra-download.ncbi.nlm.nih.gov' in url:
    #        run_accession_to_downloadble_file_url_dict[accession] = url


    SAMPLE = EXPERIMENT_PACKAGE.find('SAMPLE')
    SAMPLE_ATTRIBUTE_list = SAMPLE.iter('SAMPLE_ATTRIBUTE')

    for SAMPLE_ATTRIBUTE in SAMPLE_ATTRIBUTE_list:
        VALUE = SAMPLE_ATTRIBUTE.find('VALUE')
        if VALUE is not None:
            TAG_text = SAMPLE_ATTRIBUTE.find('TAG').text
            VALUE_text = VALUE.text

            if TAG_text in ['host', 'host scientific name']:
                if VALUE_text.lower() in ['homo sapien', 'homosapiens']:
                    VALUE_text = 'Homo sapiens'

                if VALUE_text in field_to_term_to_uri_dict['ncbi_host_species']:
                    info_for_yaml_dict['host']['host_species'] = field_to_term_to_uri_dict['ncbi_host_species'][VALUE_text]
                else:
                    missing_value_list.append('\t'.join([accession, 'host_species', VALUE_text]))
            elif TAG_text in ['host_health_status', 'host health state']:
                if VALUE_text in field_to_term_to_uri_dict['ncbi_host_health_status']:
                    info_for_yaml_dict['host']['host_health_status'] = field_to_term_to_uri_dict['ncbi_host_health_status'][VALUE_text]
                elif VALUE_text.strip("'") not in ['missing', 'not collected', 'not provided']:
                    missing_value_list.append('\t'.join([accession, 'host_health_status', VALUE_text]))
            elif TAG_text in ['strain', 'isolate']:
                if VALUE_text.lower() not in ['not applicable', 'missing', 'na', 'unknown', 'not provided']:
                    value_to_insert = VALUE_text

                    if value_to_insert.lower() in ['homo sapien', 'homosapiens']:
                        value_to_insert = 'Homo sapiens'

                    if value_to_insert in field_to_term_to_uri_dict['ncbi_host_species']:
                        value_to_insert = field_to_term_to_uri_dict['ncbi_host_species'][value_to_insert]

                    if 'virus_strain' not in info_for_yaml_dict:
                        info_for_yaml_dict['virus']['virus_strain'] = value_to_insert
                    else:
                        info_for_yaml_dict['virus']['virus_strain'] += '; ' + value_to_insert
            elif TAG_text in ['isolation_source', 'isolation source host-associated']:
                if VALUE_text in field_to_term_to_uri_dict['ncbi_speciesman_source']:
                    info_for_yaml_dict['sample']['specimen_source'] = [field_to_term_to_uri_dict['ncbi_speciesman_source'][VALUE_text]]
                else:
                    if VALUE_text.lower() in ['np/op', 'np-op', 'np/op swab', 'np/np swab', 'nasopharyngeal and oropharyngeal swab', 'nasopharyngeal/oropharyngeal swab', 'combined nasopharyngeal and oropharyngeal swab', 'naso and/or oropharyngeal swab']:
                        info_for_yaml_dict['sample']['specimen_source'] = [field_to_term_to_uri_dict['ncbi_speciesman_source']['nasopharyngeal swab'], field_to_term_to_uri_dict['ncbi_speciesman_source']['oropharyngeal swab']]
                    elif VALUE_text.lower() in ['nasopharyngeal swab/throat swab', 'nasopharyngeal/throat swab', 'nasopharyngeal swab and throat swab', 'nasal swab and throat swab', 'nasopharyngeal aspirate/throat swab', 'Nasopharyngeal/Throat']:
                        info_for_yaml_dict['sample']['specimen_source'] = [field_to_term_to_uri_dict['ncbi_speciesman_source']['nasopharyngeal swab'], field_to_term_to_uri_dict['ncbi_speciesman_source']['throat swab']]
                    elif VALUE_text.lower() in ['nasopharyngeal aspirate & throat swab', 'nasopharyngeal aspirate and throat swab']:
                        info_for_yaml_dict['sample']['specimen_source'] = [field_to_term_to_uri_dict['ncbi_speciesman_source']['nasopharyngeal aspirate'], field_to_term_to_uri_dict['ncbi_speciesman_source']['throat swab']]
                    elif VALUE_text.lower() in ['nasal swab and throat swab']:
                        info_for_yaml_dict['sample']['specimen_source'] = [field_to_term_to_uri_dict['ncbi_speciesman_source']['nasal swab'], field_to_term_to_uri_dict['ncbi_speciesman_source']['throat swab']]
                    elif VALUE_text.lower() in ['nasal-swab and oro-pharyngeal swab']:
                        info_for_yaml_dict['sample']['specimen_source'] = [field_to_term_to_uri_dict['ncbi_speciesman_source']['nasal swab'], field_to_term_to_uri_dict['ncbi_speciesman_source']['oropharyngeal swab']]
                    elif VALUE_text.strip("'") not in ['missing', 'not collected', 'unknown', 'not provided', 'not applicable', 'N/A']:
                        missing_value_list.append('\t'.join([accession, 'specimen_source', VALUE_text]))
            elif TAG_text in ['host_sex', 'host sex']:
                if VALUE_text.lower() not in ['missing', 'not provided']:
                    if VALUE_text in ['male', 'female']:
                        info_for_yaml_dict['host']['host_sex'] = "http://purl.obolibrary.org/obo/PATO_0000384" if VALUE_text == 'male' else "http://purl.obolibrary.org/obo/PATO_0000383"
                    else:
                        missing_value_list.append('\t'.join([accession, 'host_sex', VALUE_text]))
            elif TAG_text in ['host_age', 'host age']:
                if is_integer(VALUE_text):
                    host_age = int(VALUE_text)
                    if host_age >= 0 and host_age < 110:
                        info_for_yaml_dict['host']['host_age'] = host_age
                        info_for_yaml_dict['host']['host_age_unit'] = 'http://purl.obolibrary.org/obo/UO_0000036'
            elif TAG_text == 'collected_by':
                if VALUE_text.lower() not in ['not available', 'missing']:
                    name = VALUE_text in ['Dr. Susie Bartlett', 'Ahmed Babiker', 'Aisi Fu', 'Brandi Williamson', 'George Taiaroa', 'Natacha Ogando', 'Tim Dalebout', 'ykut Ozdarendeli']

                    info_for_yaml_dict['sample']['collector_name' if name else 'collecting_institution'] = VALUE_text
            elif TAG_text == 'collecting institution':
                if VALUE_text.lower() not in ['not provided', 'na']:
                    info_for_yaml_dict['sample']['collecting_institution'] = VALUE_text
            elif TAG_text in ['collection_date', 'collection date']:
                if VALUE_text.lower() not in ['not applicable', 'missing', 'na']:
                    date_to_write = VALUE_text
                    date_is_estimated = True

                    VALUE_text_list = VALUE_text.split('-')
                    if len(VALUE_text_list) == 3:
                        date_is_estimated = False

                        if VALUE_text_list[1].isalpha():
                            date_to_write = parse(VALUE_text).strftime('%Y-%m-%d')
                    elif len(VALUE_text_list) == 2:
                        date_to_write = parse(VALUE_text).strftime('%Y-%m') + '-15'
                    else:
                        if int(VALUE_text) < 2020:
                            date_to_write = "{}-12-15".format(VALUE_text)
                        else:
                            date_to_write = "{}-01-15".format(VALUE_text)

                    info_for_yaml_dict['sample']['collection_date'] = date_to_write

                    if date_is_estimated:
                        if 'additional_collection_information' in info_for_yaml_dict['sample']:
                            info_for_yaml_dict['sample']['additional_collection_information'] += "; The 'collection_date' is estimated (the original date was: {})".format(VALUE_text)
                        else:
                            info_for_yaml_dict['sample']['additional_collection_information'] = "The 'collection_date' is estimated (the original date was: {})".format(VALUE_text)
            elif TAG_text in ['geo_loc_name', 'geographic location (country and/or sea)', 'geographic location (region and locality)']:
                if ': ' in VALUE_text:
                    VALUE_text = VALUE_text.replace(': ', ':')

                if VALUE_text in field_to_term_to_uri_dict['ncbi_countries']:
                    info_for_yaml_dict['sample']['collection_location'] = field_to_term_to_uri_dict['ncbi_countries'][VALUE_text]
                elif VALUE_text.lower() not in ['na', 'not applicable']:
                    missing_value_list.append('\t'.join([accession, 'geo_loc_name', VALUE_text]))
            #else:
            #    if TAG_text not in ['lat_lon', 'host_disease', 'BioSampleModel', 'passage_history']:
            #        print(accession, TAG_text, VALUE_text)


    taxon_id = SAMPLE.find('SAMPLE_NAME').find('TAXON_ID').text
    info_for_yaml_dict['virus']['virus_species'] = "http://purl.obolibrary.org/obo/NCBITaxon_" + taxon_id

    # This script download and prepare data and metadata for samples that will be mapped against a referenceT
    info_for_yaml_dict['technology']['assembly_method'] = 'http://purl.obolibrary.org/obo/GENEPIO_0002028'

    EXPERIMENT = EXPERIMENT_PACKAGE.find('EXPERIMENT')
    INSTRUMENT_MODEL = [x.text for x in EXPERIMENT.find('PLATFORM').iter('INSTRUMENT_MODEL')][0]

    if INSTRUMENT_MODEL.lower() != 'unspecified':
        if INSTRUMENT_MODEL in field_to_term_to_uri_dict['ncbi_sequencing_technology']:
            info_for_yaml_dict['technology']['sample_sequencing_technology'] = [field_to_term_to_uri_dict['ncbi_sequencing_technology'][INSTRUMENT_MODEL]]
        else:
            missing_value_list.append('\t'.join([accession, 'sample_sequencing_technology', INSTRUMENT_MODEL]))
    #else:
    #    print(accession, 'Missing INSTRUMENT_MODEL', info_for_yaml_dict)
    LIBRARY_DESCRIPTOR = EXPERIMENT.find('DESIGN').find('LIBRARY_DESCRIPTOR')
    if LIBRARY_DESCRIPTOR.text not in ['', 'OTHER']:
        info_for_yaml_dict['technology']['additional_technology_information'] = 'LIBRARY_STRATEGY: {};'.format(LIBRARY_DESCRIPTOR.find('LIBRARY_STRATEGY').text)

    SUBMISSION = EXPERIMENT_PACKAGE.find('SUBMISSION')
    if SUBMISSION.attrib['accession']:
        info_for_yaml_dict['submitter']['submitter_sample_id'] = SUBMISSION.attrib['accession']

    if SUBMISSION.attrib['lab_name'].lower() not in ['', 'na']:
        info_for_yaml_dict['submitter']['originating_lab'] = SUBMISSION.attrib['lab_name']

    STUDY = EXPERIMENT_PACKAGE.find('STUDY')
    if STUDY.attrib['alias']:
        info_for_yaml_dict['submitter']['publication'] = STUDY.attrib['alias']


    Organization = EXPERIMENT_PACKAGE.find('Organization')
    Organization_Name = Organization.find('Name')
    if Organization_Name.text:
        info_for_yaml_dict['submitter']['authors'] = [Organization_Name.text]

    Organization_Contact = Organization.find('Contact')
    if Organization_Contact is not None:
        Organization_Contact_Name = Organization_Contact.find('Name')
        info_for_yaml_dict['submitter']['submitter_name'] = [Organization_Contact_Name.find('First').text + ' ' + Organization_Contact_Name.find('Last').text]
        info_for_yaml_dict['submitter']['additional_submitter_information'] = Organization_Contact.attrib['email']

        Organization_Concact_Address = Organization_Contact.find('Address')
        if Organization_Concact_Address is not None:
            info_for_yaml_dict['submitter']['submitter_address'] = '; '.join([x.text for x in Organization_Concact_Address] + ['Postal code ' + Organization_Concact_Address.attrib['postal_code']])

    Organization_Address = Organization.find('Address')
    if Organization_Address is not None:
        info_for_yaml_dict['submitter']['lab_address'] = '; '.join([x.text for x in Organization_Address] + ['Postal code ' + Organization_Address.attrib['postal_code']])

    # Do not trick the quality control!
    #if 'collection_date' not in info_for_yaml_dict['sample']:
    #    info_for_yaml_dict['sample']['collection_date'] = '1970-01-01'
    #    info_for_yaml_dict['sample']['additional_collection_information'] = "The real 'collection_date' is missing"

    # Check if mandatory fields are missing
    if 'collection_date' not in info_for_yaml_dict['sample']:
        # print(accession_version, ' - collection_date not found')
        if accession not in not_created_accession_dict:
            not_created_accession_dict[accession] = []
        not_created_accession_dict[accession].append('collection_date not found')
    else:
        year, month, day = [int(x) for x in info_for_yaml_dict['sample']['collection_date'].split('-')]

        collection_date_in_yaml = datetime(year, month, day)
        if collection_date_in_yaml < min_acceptable_collection_date:
            if accession not in not_created_accession_dict:
                not_created_accession_dict[accession] = []
            not_created_accession_dict[accession].append('collection_date too early')

    if 'sample_sequencing_technology' not in info_for_yaml_dict['technology']:
        # print(accession_version, ' - technology not found')
        if accession not in not_created_accession_dict:
            not_created_accession_dict[accession] = []
        not_created_accession_dict[accession].append('sample_sequencing_technology not found')

    if 'collection_location' not in info_for_yaml_dict['sample']:
        if accession not in not_created_accession_dict:
            not_created_accession_dict[accession] = []
        not_created_accession_dict[accession].append('collection_location not found')

    if 'collection_date' not in info_for_yaml_dict['sample']:
        if accession not in not_created_accession_dict:
            not_created_accession_dict[accession] = []
        not_created_accession_dict[accession].append('collection_date not found')

    if 'authors' not in info_for_yaml_dict['submitter']:
        if accession not in not_created_accession_dict:
            not_created_accession_dict[accession] = []
        not_created_accession_dict[accession].append('authors not found')

    if 'host_species' not in info_for_yaml_dict['host']:
        if accession not in not_created_accession_dict:
            not_created_accession_dict[accession] = []
        not_created_accession_dict[accession].append('host_species not found')

    if accession not in not_created_accession_dict:
        num_yaml_created += 1

        with open(os.path.join(dir_yaml, '{}.yaml'.format(accession)), 'w') as fw:
            json.dump(info_for_yaml_dict, fw, indent=2)

if len(missing_value_list) > 0:
    path_missing_terms_tsv = 'missing_terms.sra.tsv'
    print('Written missing terms in {}'.format(path_missing_terms_tsv))
    with open(path_missing_terms_tsv, 'w') as fw:
        fw.write('\n'.join(missing_value_list))

if len(not_created_accession_dict) > 0:
    path_not_created_accession_tsv = 'not_created_accession.sra.tsv'
    print('Written not created accession in {}'.format(path_not_created_accession_tsv))
    with open(path_not_created_accession_tsv, 'w') as fw:
        fw.write('\n'.join(['\t'.join([accession_version, ','.join(missing_info_list)]) for accession_version, missing_info_list in not_created_accession_dict.items()]))

print('Num. YAML files created: {}'.format(num_yaml_created))
