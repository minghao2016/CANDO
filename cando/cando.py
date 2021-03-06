import os
import requests
import random
import time
import operator
import math
import progressbar
import numpy as np
import pandas as pd
import multiprocessing as mp
import pybel
import difflib
import matplotlib.pyplot as plt
from rdkit import Chem, DataStructs, RDConfig
from rdkit.Chem import AllChem, rdmolops
from sklearn.metrics import pairwise_distances, roc_curve, roc_auc_score, average_precision_score
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn import svm
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from scipy.spatial.distance import squareform


class Protein(object):
    """!
    An object to represent a protein
    """
    def __init__(self, id_, sig):
        ## @var id_ 
        #   PDB or UniProt ID for the given protein
        self.id_ = id_
        ## @alt_id
        #   Used when a second identifer mapping is available (such as SIFTs project)
        self.alt_id = ''
        ## @var sig 
        #   List of scores representing each drug interaction with the given protein
        self.sig = sig
        ## @var pathways 
        #   List of Pathway objects in which the given protein is involved.
        self.pathways = []


class Compound(object):
    """!
    An object to represent a compound/drug
    """
    def __init__(self, name, id_, index):
        ## @var name 
        # str: Name of the Compound (e.g., 'caffeine')
        self.name = name
        ## @var id_
        # int: CANDO id from mapping file (e.g., 1, 10, 100, ...)
        self.id_ = id_
        ## @var index
        # int: The order in which the Compound appears in the mapping file (e.g, 1, 2, 3, ...)
        self.index = index
        ## @var sig
        # list: Signature is essentially a column of the Matrix
        self.sig = []
        ## @var aux_sig
        # list: Potentially temporary signature for things like pathways, where "c.sig" needs to be preserved
        self.aux_sig = []
        ## @var indications
        # list: This is every indication the Compound is associated with from the
        # mapping file
        self.indications = []
        ## @var similar
        # list: This is the ranked list of compounds with the most similar interaction signatures
        self.similar = []
        ## @var similar_computed
        # bool: Have the distances of all Compounds to the given Compound been computed?
        self.similar_computed = False
        ## @var similar_sorted
        # bool: Have the most similar Compounds to the given Compound been sorted?
        self.similar_sorted = False
        ## @var cluster_id
        # int: The cluster id this Compound was assigned from clustering method
        self.cluster_id = []
        ## @var adrs
        # list: List of ADRs associated with this Compound
        self.adrs = []

    def add_indication(self, ind):
        """!
        Add an Indication to the list of Indications associated to this Compound

        @param ind object: Indication object to add
        """
        self.indications.append(ind)


class Indication(object):
    """!
    An object to represent an indication (disease)
    """
    def __init__(self, ind_id, name):
        ## @var id_
        # str: MeSH or OMIM ID for the indication from the mapping file
        self.id_ = ind_id
        ## @var name
        # str: Name for the indication from the mapping file
        self.name = name
        ## @var compounds
        # list: Every associated compound object from the mapping file
        self.compounds = []
        ## @var pathways
        # list: Every pathway associated to the indication from the mapping file
        self.pathways = []
        ## @var proteins
        # list: Every protein associated to the indication form the mapping file
        self.proteins = []
        ## @var pathogen
        # bool: Whether or not this indication is caused by a pathogen
        self.pathogen = None


class Pathway(object):
    """!
    An object to represent a pathway
    """
    def __init__(self, id_):
        ## @var proteins
        # list: Protein objects associated with the given Pathway
        self.proteins = []
        ## @var id_
        # str: Identification for the given Pathway
        self.id_ = id_
        ## @var indications
        # list: Indication objects associated with the given Pathway
        self.indications = []


class ADR(object):
    """!
    An object to represent an adverse reaction
    """
    def __init__(self, id_, name):
        ## @var id_
        # str: Identification for the given ADR
        self.id_ = id_
        ## @var name
        # str: Name of the given ADR
        self.name = name
        ## @var compounds
        # list: Compound objects associated with the given ADR
        self.compounds = []


class CANDO(object):
    """!
    An object to represent all aspects of CANDO (compounds, indications, matrix, etc.)

    To instantiate you need the compound mapping (c_map),
    indication mapping file (i_map), and a compound-protein matrix (matrix=) or
    or precomputed compound-compound distance matrix (read_rmsds=)

    """
    def __init__(self, c_map, i_map, matrix='', compute_distance=False, save_rmsds='', read_rmsds='',
                 pathways='', pathway_quantifier='max', indication_pathways='', indication_proteins='',
                 similarity=False, dist_metric='rmsd', protein_set='', rm_zeros=False, rm_compounds='',
                 adr_map='', ncpus=1):
        ## @var c_map 
        # str: File path to the compound mapping file (relative or absolute)
        self.c_map = c_map
        ## @var i_map 
        # str: File path to the indication mapping file (relative or absolute)
        self.i_map = i_map
        ## @var matrix 
        # str: File path to the cando matrix file (relative or absolute)
        self.matrix = matrix
        ## @var protein_set
        # str: File path to protein subset file (relative or absolute) 
        self.protein_set = protein_set
        ## @var pathways
        # str: File path to pathway file
        self.pathways = []
        self.accuracies = {}
        ## @var compute_distance
        # bool: Calculate the distance for each Compound against all other Compounds using chosen distance metric
        self.compute_distance = compute_distance
        self.clusters = {}
        ## @var rm_zeros
        # bool: Remove Compounds with all-zero signatures from CANDO object
        self.rm_zeros = rm_zeros
        ## @var rm_compounds
        # list: Compounds to remove from the CANDO object 
        self.rm_compounds = rm_compounds
        self.rm_cmpds = []
        ## @var save_rmsds
        # bool: Write the calculated distances to file after computation (set compute_distances=True)
        self.save_rmsds = save_rmsds
        ## @var read_rmsds
        # str: File path to pre-computed distance matrix
        self.read_rmsds = read_rmsds
        ## @var similarity
        # bool: Use similarity instead of distance
        self.similarity = similarity
        ## @var dist_metric
        # str: Distance metric to be used for computing Compound-Compound distances
        self.dist_metric = dist_metric
        ## @var ncpus
        # int: Numebr of CPUs used for parallelization
        self.ncpus = int(ncpus)
        ## @var pathway_quantifier
        # str: Method used to quantify a all Pathways
        self.pathway_quantifier = pathway_quantifier
        ## @var indication_pathways
        # str: File path to Indication-Pathway association file
        self.indication_pathways = indication_pathways
        ## @var indication_proteins
        # str: File path to Indication-Protein association file
        self.indication_proteins = indication_proteins
        ## @var adr_map
        # str: File path to ADR mapping file
        self.adr_map = adr_map

        self.proteins = []
        self.protein_id_to_index = {}
        self.compounds = []
        self.indications = []
        self.indication_ids = []
        self.adrs = []

        self.short_matrix_path = self.matrix.split('/')[-1]
        self.short_read_rmsds = read_rmsds.split('/')[-1]
        self.short_protein_set = protein_set.split('/')[-1]
        self.cmpd_set = rm_compounds.split('/')[-1]
        self.data_name = ''

        if self.matrix:
            if self.protein_set:
                self.data_name = self.short_protein_set + '.' + self.short_matrix_path
            elif rm_compounds:
                self.data_name = self.cmpd_set + '.' + self.short_matrix_path
        if self.short_read_rmsds:
            self.data_name = self.short_read_rmsds

        # create all of the compound objects from the compound map
        with open(c_map, 'r') as c_f:
            for l in c_f.readlines():
                ls = l.strip().split('\t')
                if len(ls) == 3:
                    name = ls[2]
                    id_ = int(ls[1])
                    index = int(ls[0])
                # Used for the v2 mappings
                # These only have 2 columns [id/index,name]
                elif len(ls) == 2:
                    name = ls[1]
                    id_ = int(ls[0])
                    index = int(ls[0])
                else:
                    print("Check the number of columns for the compound mapping.")
                cm = Compound(name, id_, index)
                self.compounds.append(cm)

        # create the indication objects and add indications to the
        # already created compound objects from previous loop
        # NOTE: if a compound is in the indication mapping file that
        # isn't in the compound mapping file, an error will occur. I
        # had to remove those compounds from the indication mapping in
        # order for it to work
        with open(i_map, 'r') as i_f:
            for l in i_f.readlines():
                ls = l.strip().split('\t')
                c_id = int(ls[1])
                i_name = ls[2]
                ind_id = ls[3]
                cm = self.get_compound(c_id)
                if cm:
                    if ind_id in self.indication_ids:
                        ind = self.get_indication(ind_id)
                        ind.compounds.append(cm)
                    else:
                        ind = Indication(ind_id, i_name)
                        ind.compounds.append(cm)
                        self.indications.append(ind)
                        self.indication_ids.append(ind.id_)
                    cm.add_indication(ind)

        # add proteins, add signatures and such to compounds
        if self.protein_set:
            uniprots = []
            with open(self.protein_set, 'r') as psf:
                lines = psf.readlines()
                for line in lines:
                    uni = line.strip()
                    uniprots.append(uni)

        if matrix:
            if matrix[-4:] == '.fpt':
                print('The matrix file {} is in the old fpt format -- please '
                      'convert to tsv with the following line of code:'.format(matrix))
                print('>> Matrix({}, convert_to_tsv=True)'.format(matrix))
                quit()
            print('Reading signatures from matrix...')

            with open(matrix, 'r') as m_f:
                m_lines = m_f.readlines()
                if self.protein_set:
                    print('Editing signatures according to proteins in {}...'.format(self.protein_set))
                    targets, pdct_rev = self.uniprot_set_index(self.protein_set)
                    new_i = 0
                    matches = [[], 0]
                    for l_i in range(len(m_lines)):
                        vec = m_lines[l_i].strip().split('\t')
                        name = vec[0]
                        if name in targets:
                            scores = list(map(float, vec[1:]))
                            p = Protein(name, scores)
                            alt = pdct_rev[name]
                            p.alt_id = alt
                            if alt in matches[0]:
                                matches[1] += 1
                            else:
                                matches[0].append(alt)
                                matches[1] += 1
                            self.proteins.append(p)
                            self.protein_id_to_index[name] = new_i
                            for i in range(len(scores)):
                                s = scores[i]
                                self.compounds[i].sig.append(s)
                            new_i += 1
                        else:
                            continue
                    print('{} proteins in {} mapped to {} proteins '
                          'in {}.'.format(len(matches[0]), self.protein_set, matches[1], self.matrix))
                else:
                    for l_i in range(len(m_lines)):
                        vec = m_lines[l_i].strip().split('\t')
                        name = vec[0]
                        scores = list(map(float, vec[1:]))
                        p = Protein(name, scores)
                        self.proteins.append(p)
                        self.protein_id_to_index[name] = l_i
                        for i in range(len(scores)):
                            s = scores[i]
                            self.compounds[i].sig.append(s)
            print('Done reading signatures.\n')
        if pathways:
            print('Reading pathways...')
            if self.indication_pathways:
                print('Reading indication-pathway associations...')
                path_ind = {}
                with open(indication_pathways, 'r') as ipf:
                    for l in ipf:
                        ls = l.strip().split('\t')
                        pw = ls[0]
                        ind_ids = ls[1:]
                        path_ind[pw] = ind_ids

            with open(pathways, 'r') as pf:
                for l in pf:
                    ls = l.strip().split('\t')
                    pw = ls[0]
                    ps = ls[1:]
                    if not ps:
                        continue
                    PW = Pathway(pw)
                    self.pathways.append(PW)
                    for p in ps:
                        try:
                            pi = self.protein_id_to_index[p]
                            pro = self.proteins[pi]
                            pro.pathways.append(PW)
                            PW.proteins.append(pro)
                        except KeyError:
                            pass

                    if self.indication_pathways:
                        try:
                            ind_ids = path_ind[pw]
                            for ind_id in ind_ids:
                                try:
                                    ind = self.get_indication(ind_id)
                                except LookupError:
                                    continue
                                PW.indications.append(ind)
                                ind.pathways.append(PW)
                        except KeyError:
                            continue
            if not indication_pathways:
                self.quantify_pathways()
            print('Done reading pathways.')

        if self.indication_proteins:
            print('Reading indication-gene associations...')
            with open(indication_proteins, 'r') as igf:
                for l in igf:
                    ls = l.strip().split('\t')
                    ind_id = ls[0]
                    genes = ls[1].split(";")
                    for p in genes:
                        try:
                            pi = self.protein_id_to_index[p]
                            pro = self.proteins[pi]
                            ind = self.get_indication(ind_id)
                            ind.proteins.append(pro)
                        except KeyError:
                            pass
            print('Done reading indication-gene associations.')

        if read_rmsds:
            print('Reading RMSDs...')
            with open(read_rmsds, 'r') as rrs:
                lines = rrs.readlines()
                for i in range(len(lines)):
                    c1 = self.compounds[i]
                    scores = lines[i].strip().split('\t')
                    for j in range(len(scores)):
                        if i == j:
                            continue
                        else:
                            s = float(scores[j])
                            if similarity:
                                s = 1 - s
                            c1.similar.append((self.compounds[j], s))
            for c in self.compounds:
                sorted_scores = sorted(c.similar, key=lambda x: x[1] if not math.isnan(x[1]) else 100000)
                c.similar = sorted_scores
                c.similar_computed = True
                c.similar_sorted = True
            print('Done reading RMSDs.')

        if rm_compounds:
            print('Removing undesired compounds in {}...'.format(rm_compounds))
            with open(rm_compounds, 'r') as rcf:
                for line in rcf:
                    cmpd_id = int(line.strip().split('\t')[0])
                    self.rm_cmpds.append(cmpd_id)
            good_cmpds = []
            for c in self.compounds:
                if c.id_ in self.rm_cmpds:
                    pass
                else:
                    good_cmpds.append(c)
            self.compounds = good_cmpds
            for c in self.compounds:
                good_sims = []
                for s in c.similar:
                    if s[0].id_ in self.rm_cmpds:
                        pass
                    else:
                        good_sims.append(s)
                c.similar = good_sims
            print('Done removing undesired compounds.')

        # if compute distance is true, generate similar compounds for each
        if compute_distance and not read_rmsds:
            if self.pathways and not self.indication_pathways:
                print('Computing distances using global pathway signatures...')
                for c in self.compounds:
                    self.generate_similar_sigs(c, aux=True)
            else:
                print('Computing {} distances...'.format(self.dist_metric))
                # put all compound signatures into 2D-array
                signatures = []
                for i in range(0, len(self.compounds)):
                    signatures.append(self.compounds[i].sig)
                snp = np.array(signatures)  # convert to numpy form

                # call pairwise_distances, speed up with custom RMSD function and parallelism
                if self.dist_metric == "rmsd":
                    distance_matrix = pairwise_distances(snp, metric=lambda u, v: np.sqrt(((u - v) ** 2).mean()), n_jobs=self.ncpus)
                    distance_matrix = squareform(distance_matrix)
                elif self.dist_metric in ['cosine', 'correlation', 'euclidean', 'cityblock']:
                    distance_matrix = pairwise_distances(snp, metric=self.dist_metric, n_jobs=self.ncpus)
                    # Removed checks in case the diagonal is very small (close to zero) but not zero.
                    distance_matrix = squareform(distance_matrix, checks=False)
                else:
                    print("Incorrect distance metric - {}".format(self.dist_metric))
                    exit()

                # step through the condensed matrix - add RMSDs to Compound.similar lists
                nc = len(self.compounds)
                n = 0
                for i in range(nc):
                    for j in range(i, nc):
                        c1 = self.compounds[i]
                        c2 = self.compounds[j]
                        if i == j:
                            continue
                        r = distance_matrix[n]
                        c1.similar.append((c2, r))
                        c2.similar.append((c1, r))
                        n += 1
                print('Done computing {} distances.'.format(self.dist_metric))

            if self.save_rmsds:

                def rmsds_to_str(cmpd, ci):
                    o = ''
                    for si in range(len(cmpd.similar)):
                        if ci == si:
                            if self.similarity:
                                o += '1.0\t'
                            else:
                                o += '0.0\t'
                        s = cmpd.similar[si]
                        o += '{}\t'.format(s[1])
                    o = o[:-1] + '\n'
                    return o

                with open(self.save_rmsds, 'w') as srf:
                    for ci in range(len(self.compounds)):
                        c = self.compounds[ci]
                        srf.write(rmsds_to_str(c, ci))
                print('RMSDs saved.')

            # sort the RMSDs after saving (if desired)
            for c in self.compounds:
                sorted_scores = sorted(c.similar, key=lambda x: x[1] if not math.isnan(x[1]) else 100000)
                c.similar = sorted_scores
                c.similar_computed = True
                c.similar_sorted = True

        if self.rm_zeros:
            print('Removing compounds with all-zero signatures...')

            def check_sig(sig):
                for s in sig:
                    if s != 0.0:
                        return True
                return False

            non_zero_compounds = []
            for c in self.compounds:
                if check_sig(c.sig):
                    non_zero_compounds.append(c)
            self.compounds = non_zero_compounds
            print('Done removing compounds with all-zero signatures.')

        if self.rm_zeros or self.rm_compounds:
            print('Filtering indication mapping...')
            for ind in self.indications:
                good_cmpds = []
                for cmpd in ind.compounds:
                    if cmpd.id_ in self.rm_cmpds:
                        pass
                    else:
                        good_cmpds.append(cmpd)
                ind.compounds = good_cmpds
            print('Done filtering indication mapping.')

        if adr_map:
            print('Reading ADR mapping file...')
            with open(adr_map, 'r') as amf:
                for l in amf:
                    ls = l.strip().split('\t')
                    c_index = int(ls[1])
                    cmpd = self.compounds[c_index]
                    adr_id = ls[4]
                    adr_name = ls[3]
                    try:
                        adr = self.get_adr(adr_id)
                        adr.compounds.append(cmpd)
                        cmpd.adrs.append(adr)
                    except LookupError:
                        adr = ADR(adr_id, adr_name)
                        adr.compounds.append(cmpd)
                        cmpd.adrs.append(adr)
                        self.adrs.append(adr)
            print('Read {} ADRs.'.format(len(self.adrs)))

    def search_compound(self, name, n=5):
        id_d = {}

        def return_names(x):
            id_d[x.name] = x.id_
            return x.name

        name = name.strip()
        cando_drugs = list(map(return_names, self.compounds))
        nms = difflib.get_close_matches(name, cando_drugs, n=n, cutoff=0.5)
        print('Query: {}'.format(name))
        print('\tMatch name\tID/Index')
        for nm in nms:
            print("\t{}\t{}".format(nm, id_d[nm]))

    def get_compound(self, id_=None, name=''):
        """!
        Get Compound object from Compound id

        @param id_ int: Compound id
        @param name str: name of drug (must match exactly)
        @return Returns object: Compound object
        """
        if id_ is not None:
            for c in self.compounds:
                if c.id_ == id_:
                    return c
            print("{0} not in {1}".format(id_, self.c_map))
            return None
        else:
            id_d = {}

            def return_names(x):
                id_d[x.name] = x.id_
                return x.name

            cando_drugs = list(map(return_names, self.compounds))
            name = name.strip()
            if name not in cando_drugs:
                print('"{}" is not in our mapping, here are the 5 closest results:'.format(name))
                self.search_compound(name, n=5)
                return None
            else:
                return self.get_compound(id_=id_d[name])

    def get_indication(self, ind_id):
        """!
        Get Indication object from Indication id

        @param ind_id str: Indication id
        @return Returns object: Indication object
        """
        for i in self.indications:
            if i.id_ == ind_id:
                return i
        raise LookupError

    def get_pathway(self, id_):
        """!
        Get Pathway object from Pathway id

        @param id_ str: Pathway id
        @return Returns object: Pathway object
        """
        for p in self.pathways:
            if p.id_ == id_:
                return p
        raise LookupError

    def get_adr(self, id_):
        """!
        Get ADR (adverse drug reaction) from ADR id
        
        @param id_ str: ADR id
        @return Returns object: ADR object
        """
        for a in self.adrs:
            if a.id_ == id_:
                return a
        raise LookupError

    def top_targets(self, cmpd, n=10, negative=False):
        """!
        Get the top scoring protein targets for a given compound

        @param cmpd Compound: Compound object for which to print targets
        @param n int: number of top targets to print/return
        @param negative int: if the interaction scores are negative (stronger) energies
        @return Returns list: list of tuples (protein id_, score)
        """
        # print the list of the top targets
        all_interactions = []
        sig = cmpd.sig
        for i in range(len(sig)):
            s = sig[i]
            p_id = self.proteins[i].id_
            all_interactions.append((p_id, s))
        if negative:
            interactions_sorted = sorted(all_interactions, key=lambda x: x[1])
        else:
            interactions_sorted = sorted(all_interactions, key=lambda x: x[1])[::-1]
        print('Compound is {}'.format(cmpd.name))
        m = len(self.proteins)
        if n > m:
            print('There are only {} proteins in this CANDO object, printing all.'.format(m))
            n = m
        for si in range(n):
            print(interactions_sorted[si][0], interactions_sorted[si][1])
        return interactions_sorted[0:n]

    def uniprot_set_index(self, prots):
        """!
        Gather proteins from input matrix that map to UniProt IDs from 'protein_set=' param

        @param prots list: UniProt IDs (str)
        @return Returns list: Protein chains (str) matching input UniProt IDs
        """
        if not os.path.exists('v2.0/mappings/pdb_2_uniprot.csv'):
            print('Downloading UniProt to PDB mapping file...')
            url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/mappings/pdb_2_uniprot.csv'
            dl_file(url, 'v2.0/mappings/pdb_2_uniprot.csv')
        pdct = {}
        pdct_rev = {}
        with open('v2.0/mappings/pdb_2_uniprot.csv', 'r') as u2p:
            for l in u2p.readlines()[1:]:
                spl = l.strip().split(',')
                pdb = spl[0] + spl[1]
                uni = spl[2]
                try:
                    if pdb not in pdct[uni]:
                        pdct[uni].append(pdb)
                except KeyError:
                    pdct[uni] = [pdb]
                pdct_rev[pdb] = uni
        targets = []
        #for tgt in prots:
        #    targets.append(tgt)
        #    pdct_rev[tgt] = tgt
        with open(prots, 'r') as unisf:
            for lp in unisf:
                prot = lp.strip()
                targets.append(prot)
                #pdct_rev[prot] = lp.strip().upper()
                try:
                    targets += pdct[lp.strip().upper()]
                except KeyError:
                    pass
        return targets, pdct_rev

    def generate_similar_sigs(self, cmpd, sort=False, proteins=[], aux=False):
        """!
        For a given compound, generate the similar compounds using distance of sigs.

        @param cmpd object: Compound object
        @param sort bool: Sort the list of similar compounds
        @param proteins list: Protein objects to identify a subset of the Compound signature
        @param aux bool: Use an auxiliary signature (default: False)

        @return Returns list: Similar Compounds to the given Compound
        """
        # find index of query compound, collect signatures for both
        q = 0
        c_sig = []
        if proteins is None:
            c_sig = cmpd.sig
        elif proteins:
            for pro in proteins:
                index = self.protein_id_to_index[pro.id_]
                c_sig.append(cmpd.sig[index])
        else:
            if aux:
                c_sig = cmpd.aux_sig
            else:
                c_sig = cmpd.sig
        ca = np.array([c_sig])

        other_sigs = []
        for ci in range(len(self.compounds)):
            c = self.compounds[ci]
            if cmpd.id_ == c.id_:
                q = ci
            other = []
            if proteins is None:
                other_sigs.append(c.sig)
            elif proteins:
                for pro in proteins:
                    index = self.protein_id_to_index[pro.id_]
                    other.append(c.sig[index])
                other_sigs.append(other)
            else:
                if aux:
                    other_sigs.append(c.aux_sig)
                else:
                    other_sigs.append(c.sig)
        oa = np.array(other_sigs)
        
        # call cdist, speed up with custom RMSD function
        if self.dist_metric == "rmsd":
            distances = pairwise_distances(ca, oa, lambda u, v: np.sqrt(((u - v) ** 2).mean()), n_jobs=self.ncpus)
        elif self.dist_metric in ['cosine', 'correlation', 'euclidean', 'cityblock']:
            distances = pairwise_distances(ca, oa, self.dist_metric, n_jobs=self.ncpus)
        else:
            print("Incorrect distance metric - {}".format(self.dist_metric))

        cmpd.similar = []
        # step through the cdist list - add RMSDs to Compound.similar list
        n = len(self.compounds)
        for i in range(n):
            c2 = self.compounds[i]
            if i == q:
                continue
            d = distances[0][i]
            cmpd.similar.append((c2, d))
            n += 1

        if sort:
            sorted_scores = sorted(cmpd.similar, key=lambda x: x[1] if not math.isnan(x[1]) else 100000)
            cmpd.similar = sorted_scores
            cmpd.similar_computed = True
            cmpd.similar_sorted = True
            return sorted_scores
        else:
            cmpd.similar_computed = True
            return cmpd.similar

    def generate_some_similar_sigs(self, cmpds, sort=False, proteins=[], aux=False):
        """!
        For a given list of compounds, generate the similar compounds based on rmsd of sigs
        This is pathways/genes for all intents and purposes

        @param cmpds list: Compound objects
        @param sort bool: Sort similar compounds for each Compound
        @param proteins list: Protein objects to identify a subset of the Compound signature
        @param aux bool: Use an auxiliary signature (default: False)

        @return Returns list: Similar Compounds to the given Compound

        """
        q = [cmpd.id_ for cmpd in cmpds]
        
        if proteins is None:
            ca = [cmpd.sig for cmpd in cmpds]
            oa = [cmpd.sig for cmpd in self.compounds]
        elif proteins:
            index = [self.protein_id_to_index[pro.id_] for pro in proteins]
            ca = [[cmpd.sig[i] for i in index] for cmpd in cmpds]
            oa = [[cmpd.sig[i] for i in index] for cmpd in self.compounds]
        else:
            if aux:
                ca = [cmpd.aux_sig for cmpd in cmpds]
                oa = [cmpd.aux_sig for cmpd in self.compounds]
            else:
                ca = [cmpd.sig for cmpd in cmpds]
                oa = [cmpd.sig for cmpd in self.compounds]
        ca = np.asarray(ca)
        oa = np.asarray(oa)
        
        # call cdist, speed up with custom RMSD function
        if self.dist_metric == "rmsd":
            distances = pairwise_distances(ca, oa, lambda u, v: np.sqrt(((u - v) ** 2).mean()), n_jobs=self.ncpus)
        elif self.dist_metric in ['cosine', 'correlation', 'euclidean', 'cityblock']:
            distances = pairwise_distances(ca, oa, self.dist_metric, n_jobs=self.ncpus)
        else:
            print("Incorrect distance metric - {}".format(self.dist_metric))

        # step through the cdist list - add RMSDs to Compound.similar list
        n = len(self.compounds)
        for j in range(len(cmpds)):
            cmpds[j].similar = []
            for i in range(n):
                c2 = self.compounds[i]
                id2 = c2.id_
                if id2 == q[j]:
                    continue
                d = distances[j][i]
                cmpds[j].similar.append((c2, d))

            if sort:
                sorted_scores = sorted(cmpds[j].similar, key=lambda x: x[1] if not math.isnan(x[1]) else 100000)
                cmpds[j].similar = sorted_scores
                cmpds[j].similar_computed = True
                cmpds[j].similar_sorted = True
            else:
                cmpds[j].similar_computed = True

    def quantify_pathways(self, indication=None):
        """!
        Uses the pathway quantifier defined in the CANDO instantiation to make a
        pathway signature for all pathways in the input file (NOTE: does not compute distances)

        @param indication object: Indication object
        """
        pq = self.pathway_quantifier
        if pq == 'max':
            func = max
        elif pq == 'sum':
            func = sum
        elif pq == 'avg':
            func = np.average
        elif pq == 'proteins':
            if not self.indication_pathways:
                print('Pathway quantifier "proteins" should only be used in combination with a '
                      'pathway-disease mapping (indication_pathways), quitting.')
                quit()
            func = None
        else:
            print('Please enter a proper pathway quantify method, quitting.')
            func = None
            quit()

        # this is a recursive function for checking if the pathways have proteins
        def check_proteins(paths):
            pl = []  # list of pathways with >1 protein
            n = 0
            for path in paths:
                if len(path.proteins) > 0:
                    pl.append(path)
                    n += 1
            if n > 0:
                return pl
            else:
                print('The associated pathways for this indication ({}) do not have enough proteins, '
                      'using all pathways'.format(indication.id_))
                return check_proteins(self.pathways)

        if indication:
            if len(indication.pathways) == 0:
                print('Warning: {} does not have any associated pathways - using all pathways'.format(indication.name))
                pws = self.pathways
            else:
                pws = check_proteins(indication.pathways)
        else:
            pws = check_proteins(self.pathways)

        for ci in range(len(self.compounds)):
            pw_sig_all = []
            c = self.compounds[ci]
            for pw in pws:
                if len(pw.proteins) == 0:
                    print('No associated proteins for pathway {}, skipping'.format(pw.id_))
                    continue
                pw_sig = []
                for p in pw.proteins:
                    ch = p.id_
                    ch_i = self.protein_id_to_index[ch]
                    pw_sig.append(c.sig[ch_i])

                if pq == 'proteins':
                    pw_sig_all += pw_sig
                else:
                    pw_sig_all.append(pw_sig)
            if pq != 'proteins':
                c.aux_sig = list(map(func, pw_sig_all))
            else:
                c.aux_sig = pw_sig_all

    def results_analysed(self, f, metrics, effect_type):
        """!
        Creates the results analysed named file for the benchmarking and
        computes final avg indication accuracies

        @param f str: File path for results analysed named
        @param metrics list: Cutoffs used for the benchmarking protocol
        @param effect_type str: Defines the effect as either an Indication (disease) or ADR (adverse reaction)
        """
        fo = open(f, 'w')
        effects = list(self.accuracies.keys())
        # Write header
        fo.write("{0}_id\tcmpds_per_{0}\ttop10\ttop25\ttop50\ttop100\ttopAll\ttop1%\t"
                 "top5%\ttop10%\ttop50%\ttop100%\t{0}_name\n".format(effect_type))
        effects_sorted = sorted(effects, key=lambda x: (len(x[0].compounds), x[0].id_))[::-1]
        l = len(effects)
        final_accs = {}
        for m in metrics:
            final_accs[m] = 0.0
        for effect, c in effects_sorted:
            fo.write("{0}\t{1}\t".format(effect.id_, c))
            accs = self.accuracies[(effect, c)]
            for m in metrics:
                n = accs[m]
                y = str(n / c * 100)[0:4]
                fo.write("{}\t".format(y))

                final_accs[m] += n / c / l
            fo.write("{}\n".format(effect.name))
        fo.close()
        return final_accs

    def canbenchmark(self, file_name, indications=[], continuous=False, bottom=False,
                     ranking='standard', adrs=False):
        """!
        Benchmarks the platform based on compound similarity of those approved for the same diseases

        @param file_name str: Name to be used for the various results files (e.g. file_name=test --> summary_test.tsv)
        @param indications list or str: List of Indication ids to be used for this benchmark, otherwise all will be used.
        @param continuous bool: Use the percentile of distances from the similarity matrix as the cutoffs for
        benchmarking
        @param bottom bool: Reverse the ranking (descending) for the benchmark
        @param ranking str: What ranking method to use for the compounds. This really only affects ties. (standard,
        modified, and ordinal)
        @param adrs bool: ADRs are used as the phenotypic effect instead of Indications
        """

        if (continuous and self.indication_pathways) or (continuous and self.indication_proteins):
            print('Continuous benchmarking and indication-based signatures are not compatible, quitting.')
            exit()

        if not self.indication_proteins and not self.indication_pathways:
            if not self.compounds[0].similar_sorted:
                for c in self.compounds:
                    sorted_scores = sorted(c.similar, key=lambda x: x[1] if not math.isnan(x[1]) else 100000)
                    c.similar = sorted_scores
                    c.similar_sorted = True

        if not os.path.exists('./results_analysed_named'):
            print("Directory 'results_analysed_named' does not exist, creating directory")
            os.system('mkdir results_analysed_named')
        if not os.path.exists('./raw_results'):
            print("Directory 'raw_results' does not exist, creating directory")
            os.system('mkdir raw_results')

        ra_named = 'results_analysed_named/results_analysed_named_' + file_name + '.tsv'
        ra = 'raw_results/raw_results_' + file_name + '.csv'
        summ = 'summary_' + file_name + '.tsv'
        ra_out = open(ra, 'w')

        def effect_type():
            if adrs:
                return 'ADR'
            else:
                return 'disease'

        def competitive_standard_bottom(sims, r):
            rank = 0
            for sim in sims:
                if sim[1] > r:
                    rank += 1.0
                else:
                    return rank
            return len(sims)

        def competitive_modified_bottom(sims, r):
            rank = 0
            for sim in sims:
                if sim[1] >= r:
                    rank += 1.0
                else:
                    return rank
            return len(sims)

        # Competitive modified ranking code
        def competitive_modified(sims, r):
            rank = 0
            for sim in sims:
                if sim[1] <= r:
                    rank += 1.0
                else:
                    return rank
            return len(sims)

        # Competitive standard ranking code
        def competitive_standard(sims, r):
            rank = 0
            for sim in sims:
                if sim[1] < r:
                    rank += 1.0
                else:
                    return rank
            return len(sims)

        def filter_indications(ind_set):
            if not os.path.exists('v2.0/mappings/group_disease-top_level.tsv'):
                url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/mappings/group_disease-top_level.tsv'
                dl_file(url, 'v2.0/mappings/group_disease-top_level.tsv')
            path_ids = ['C01', 'C02', 'C03']
            with open('v2.0/mappings/group_disease-top_level.tsv', 'r') as fgd:
                for l in fgd:
                    ls = l.strip().split('\t')
                    if ls[1] in path_ids:
                        ind = self.get_indication(ls[0])
                        ind.pathogen = True
            if ind_set == 'pathogen':
                return [indx for indx in self.indications if indx.pathogen]
            elif ind_set == 'human':
                return [indx for indx in self.indications if not indx.pathogen]
            else:
                print('Please enter proper indication set, options include "pathogen", "human", or "all".')
                quit()

        effect_dct = {}
        ss = []
        c_per_effect = 0

        if isinstance(indications, list) and len(indications) >= 1:
            effects = list(map(self.get_indication, indications))
        elif isinstance(indications, list) and len(indications) == 0:
            effects = self.indications
        elif adrs:
            effects = self.adrs
        else:
            if isinstance(indications, str):
                if indications == 'all':
                    effects = self.indications
                else:
                    effects = filter_indications(indications)

        def cont_metrics():
            all_v = []
            for c in self.compounds:
                for s in c.similar:
                    if s[1] != 0.0:
                        all_v.append(s[1])
            avl = len(all_v)
            all_v_sort = sorted(all_v)
            # for tuple 10, have to add the '-1' for index out of range reasons
            metrics = [(1, all_v_sort[int(avl/1000.0)]), (2, all_v_sort[int(avl/400.0)]), (3, all_v_sort[int(avl/200.0)]),
                       (4, all_v_sort[int(avl/100.0)]), (5, all_v_sort[int(avl/20.0)]), (6, all_v_sort[int(avl/10.0)]),
                       (7, all_v_sort[int(avl/5.0)]), (8, all_v_sort[int(avl/3.0)]), (9, all_v_sort[int(avl/2.0)]),
                       (10, all_v_sort[int(avl/1.0)-1])]
            return metrics

        x = (len(self.compounds)) / 100.0  # changed this...no reason to use similar instead of compounds
        # had to change from 100.0 to 100.0001 because the int function
        # would chop off an additional value of 1 for some reason...
        if continuous:
            metrics = cont_metrics()
        else:
            metrics = [(1, 10), (2, 25), (3, 50), (4, 100), (5, int(x*100.0001)),
                       (6, int(x*1.0001)), (7, int(x*5.0001)), (8, int(x*10.0001)),
                       (9, int(x*50.0001)), (10, int(x*100.0001))]

        if continuous:
            ra_out.write("compound_id,{}_id,0.1%({:.3f}),0.25%({:.3f}),0.5%({:.3f}),"
                         "1%({:.3f}),5%({:.3f}),10%({:.3f}),20%({:.3f}),33%({:.3f}),"
                         "50%({:.3f}),100%({:.3f}),value\n".format(effect_type(), metrics[0][1], metrics[1][1],
                                                                     metrics[2][1], metrics[3][1], metrics[4][1],
                                                                     metrics[5][1], metrics[6][1], metrics[7][1],
                                                                     metrics[8][1], metrics[9][1]))
        else:
            ra_out.write("compound_id,{}_id,top10,top25,top50,top100,"
                         "topAll,top1%,top5%,top10%,top50%,top100%,rank\n".format(effect_type()))

        for effect in effects:
            count = len(effect.compounds)
            if count < 2:
                continue
            if not adrs:
                if self.indication_pathways:
                    if len(effect.pathways) == 0:
                        print('No associated pathways for {}, skipping'.format(effect.id_))
                        continue
                    elif len(effect.pathways) < 1:
                        #print('Less than 5 associated pathways for {}, skipping'.format(effect.id_))
                        continue
            c_per_effect += count
            effect_dct[(effect, count)] = {}
            for m in metrics:
                effect_dct[(effect, count)][m] = 0.0
            # retrieve the appropriate proteins/pathway indices here, should be
            # incorporated as part of the ind object during file reading
            vs = []
            if self.pathways:
                if self.indication_pathways:
                    if self.pathway_quantifier == 'proteins':
                        for pw in effect.pathways:
                            for p in pw.proteins:
                                if p not in vs:
                                    vs.append(p)
                    else:
                        self.quantify_pathways(indication=effect)

            # Retrieve the appropriate protein indices here, should be
            # incorporated as part of the ind object during file reading
            if self.indication_proteins:
                dg = []
                for p in effect.proteins:
                    if p not in dg:
                        dg.append(p)

            c = effect.compounds
            if self.pathways:
                if self.indication_pathways:
                    if self.pathway_quantifier == 'proteins':
                        if not vs:
                            print('Warning: protein list empty for {}, using all proteins'.format(effect.id_))
                            self.generate_some_similar_sigs(c, sort=True, proteins=None, aux=True)
                        else:
                            self.generate_some_similar_sigs(c, sort=True, proteins=vs, aux=True)
                    else:
                        self.generate_some_similar_sigs(c, sort=True, aux=True)
            elif self.indication_proteins:
                if len(dg) < 2:
                    self.generate_some_similar_sigs(c, sort=True, proteins=None)
                else:
                    self.generate_some_similar_sigs(c, sort=True, proteins=dg)
            # call c.generate_similar_sigs()
            # use the proteins/pathways specified above

            for c in effect.compounds:
                for cs in c.similar:
                    if adrs:
                        if effect in cs[0].adrs:
                            cs_rmsd = cs[1]
                        else:
                            continue
                    else:
                        if effect in cs[0].indications:
                            cs_rmsd = cs[1]
                        else:
                            continue

                    value = 0.0 
                    if continuous:
                        value = cs_rmsd
                    elif bottom:
                        if ranking == 'modified':
                            value = competitive_modified_bottom(c.similar, cs_rmsd)
                        elif ranking == 'standard':
                            value = competitive_standard_bottom(c.similar, cs_rmsd)
                        elif ranking == 'ordinal':
                            value = c.similar.index(cs)
                        else:
                            print("Ranking function {} is incorrect.".format(ranking))
                            exit()
                    elif ranking == 'modified':
                        value = competitive_modified(c.similar, cs_rmsd)
                    elif ranking == 'standard':
                        value = competitive_standard(c.similar, cs_rmsd)
                    elif ranking == 'ordinal':
                        value = c.similar.index(cs)
                    else:    
                        print("Ranking function {} is incorrect.".format(ranking))
                        exit()
                   
                    if adrs:
                        s = [str(c.index), effect.name]
                    else:
                        s = [str(c.index), effect.id_]
                    for x in metrics:
                        if value <= x[1]:
                            effect_dct[(effect, count)][x] += 1.0
                            s.append('1')
                        else:
                            s.append('0')
                    if continuous:
                        s.append(str(value))
                    else:
                        s.append(str(int(value)))
                    ss.append(s)
                    break

        self.accuracies = effect_dct
        final_accs = self.results_analysed(ra_named, metrics, effect_type())
        ss = sorted(ss, key=lambda xx: int(xx[0]))
        top_pairwise = [0.0] * 10
        for s in ss:
            if s[2] == '1':
                top_pairwise[0] += 1.0
            if s[3] == '1':
                top_pairwise[1] += 1.0
            if s[4] == '1':
                top_pairwise[2] += 1.0
            if s[5] == '1':
                top_pairwise[3] += 1.0
            if s[6] == '1':
                top_pairwise[4] += 1.0
            if s[7] == '1':
                top_pairwise[5] += 1.0
            if s[8] == '1':
                top_pairwise[6] += 1.0
            if s[9] == '1':
                top_pairwise[7] += 1.0
            if s[10] == '1':
                top_pairwise[8] += 1.0
            if s[11] == '1':
                top_pairwise[9] += 1.0
            sj = ','.join(s)
            sj += '\n'
            ra_out.write(sj)
        ra_out.close()

        cov = [0] * 10
        for effect, c in list(self.accuracies.keys()):
            accs = self.accuracies[effect, c]
            for m_i in range(len(metrics)):
                v = accs[metrics[m_i]]
                if v > 0.0:
                    cov[m_i] += 1

        if continuous:
            headers = ['0.1%ile', '.25%ile', '0.5%ile', '1%ile', '5%ile',
                       '10%ile', '20%ile', '33%ile', '50%ile', '100%ile']
        else:
            headers = ['top10', 'top25', 'top50', 'top100', 'top{}'.format(len(self.compounds)),
                       'top1%', 'top5%', 'top10%', 'top50%', 'top100%']
        # Create average indication accuracy list in percent
        ia = []
        for m in metrics:
            ia.append(final_accs[m] * 100.0)
        # Create average pairwise accuracy list in percent
        pa = [(x * 100.0 / len(ss)) for x in top_pairwise]
        # Indication coverage
        cov = map(int, cov)
        # Append 3 lists to df and write to file
        with open(summ, 'w') as sf:
            sf.write("\t" + '\t'.join(headers) + '\n')
            ast = "\t".join(map(str, [format(x, ".3f") for x in ia]))
            pst = "\t".join(map(str, [format(x, ".3f") for x in pa]))
            cst = "\t".join(map(str, cov)) + '\n'
            sf.write('aia\t{}\napa\t{}\nic\t{}\n'.format(ast, pst, cst))
       
        # pretty print the average indication accuracies
        cut = 0
        print("\taia")
        for m in metrics:
            print("{}\t{:.3f}".format(headers[cut], final_accs[m] * 100.0))
            cut += 1
        print('\n')

    def canbenchmark_associated(self, file_name, indications=[], continuous=False, ranking='standard'):
        """!
        Benchmark only the compounds in the indication mapping, aka get rid of "noisy" compounds.
        This function returns the filtered CANDO object in the event that you want to explore further.

        @param file_name str: Name to be used for the variosu results files (e.g. file_name=test --> summary_test.tsv)
        @param indications list: List of Indication ids to be used for this benchmark, otherwise all will be used.
        @param continuous bool: Use the percentile of distances from the similarity matrix as the cutoffs for benchmarking
        @param ranking str: What ranking method to use for the compounds. This really only affects ties. (standard, modified, and ordinal)
        """
        print("Making CANDO copy with only benchmarking-associated compounds")
        cp = CANDO(self.c_map, self.i_map, self.matrix)
        good_cs = []
        good_ids = []
        for ind in cp.indications:
            if len(ind.compounds) >= 2:
                for c in ind.compounds:
                    if c.id_ not in good_ids:
                        good_cs.append(c)
                        good_ids.append(c.id_)
        cp.compounds = good_cs
                
        print('Computing {} distances...'.format(self.dist_metric))

        for c in cp.compounds:
            cp.generate_similar_sigs(c, sort=True)
            good_sims = []
            for s in c.similar:
                if s[0].id_ not in good_ids:
                    pass
                else:
                    good_sims.append(s)
            c.similar = good_sims
            sorted_scores = sorted(c.similar, key=lambda x: x[1] if not math.isnan(x[1]) else 100000)
            c.similar = sorted_scores
            c.similar_computed = True
            c.similar_sorted = True
        
        print('Done computing {} distances.'.format(self.dist_metric))
        
        cp.canbenchmark(file_name=file_name, indications=indications, continuous=continuous, ranking=ranking)

    def canbenchmark_bottom(self, file_name, indications=[], ranking='standard'):
        """!
        Benchmark the reverse ranking of similar compounds as a control.

        @param file_name str: Name to be used for the variosu results files (e.g. file_name=test --> summary_test.tsv)
        @param indications list: List of Indication ids to be used for this benchmark, otherwise all will be used.
        @param ranking str: What ranking method to use for the compounds. This really only affects ties. (standard,
        modified, and ordinal)
        """
        print("Making CANDO copy with reversed compound ordering")
        cp = CANDO(self.c_map, self.i_map, self.matrix)
        
        print('Computing {} distances...'.format(self.dist_metric))
        
        for ic in range(len(cp.compounds)):
            cp.generate_similar_sigs(cp.compounds[ic], sort=True)
            sorted_scores = sorted(cp.compounds[ic].similar, key=lambda x: x[1])[::-1]
            cp.compounds[ic].similar = sorted_scores
            cp.compounds[ic].similar_computed = True
            cp.similar_sorted = True
        
        print('Done computing {} distances.'.format(self.dist_metric))
        
        cp.canbenchmark(file_name=file_name, indications=indications, ranking=ranking, bottom=True)

    def canbenchmark_cluster(self, n_clusters=5):
        """!
        Benchmark using k-means clustering

        @param n_clusters int: Number of clusters for k-means
        """
        def cluster_kmeans(cmpds):
            def f(x):
                return x.sig

            def g(x):
                return x.indications

            def h(x):
                return x.id_

            sigs = np.array(list(map(f, cmpds)))
            pca = PCA(n_components=10).fit(sigs)
            sigs = pca.transform(sigs)
            inds = np.array(list(map(g, cmpds)))
            ids = np.array(list(map(h, cmpds)))
            sigs_train, sigs_test, inds_train, inds_test, ids_train, ids_test = train_test_split(sigs, inds, ids,
                                                                                                 test_size=0.20,
                                                                                                 random_state=1)
            clusters = KMeans(n_clusters, random_state=1).fit(sigs_train)
            return clusters, sigs_test, inds_train, inds_test, ids_train, ids_test

        # Calculate the K means clusters for all compound signatures
        cs, sigs_test, inds_train, inds_test, ids_train, ids_test = cluster_kmeans(self.compounds)
        labels = cs.labels_

        # Determine how many compounds are in each cluster
        # Plot the results and output the mean, median, and range
        c_clusters = [0] * n_clusters
        for l in labels:
            c_clusters[l] += 1
        '''
        all_clusters = range(n_clusters)
        plt.scatter(all_clusters,c_clusters)
        plt.text(1, 1, "Average cluster size = {}".format(np.mean(c_clusters)), horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
        plt.text(1, 1, "Median cluster size = {}".format(np.median(c_clusters)), horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
        plt.text(1, 1, "Range of cluster sizes = {}".format(np.min(c_clusters), np.max(c_clusters)), horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)
        plt.savefig("cluster_size.png")
        '''
        # Map the labels for each compound to the cluster_id for each compound object
        for ci in range(len(labels)):
            self.compounds[ids_train[ci]].cluster_id = labels[ci]

        total_acc = 0.0
        total_count = 0

        # Calculate the benchmark accuracy by
        # mimicking classic benchmark -- leave one out
        # and recapture at least one for each indication-drug pair
        for i in range(len(sigs_test)):
            lab = cs.predict(sigs_test[i].reshape(1,-1))
            for ind in inds_test[i]:
                for c in range(len(inds_train)):
                    done = False
                    for ind_train in inds_train[c]:
                        if ind.name == ind_train.name and lab[0] == labels[c]:
                            total_acc+=1.0
                            done = True
                            break
                    if done:
                        break
                total_count += 1

        print("Number of cluster = {}".format(n_clusters))
        print("Mean cluster size = {}".format(np.mean(c_clusters)))
        print("Median cluster size = {}".format(np.median(c_clusters)))
        print("Range of cluster sizes = [{},{}]".format(np.min(c_clusters), np.max(c_clusters)))
        print("% Accuracy = {}".format(total_acc / total_count * 100.0))

    def ml(self, method='rf', effect=None, benchmark=False, adrs=False, predict=[], threshold=0.5,
           negative='random', seed=42, out=''):
        """!
        create an ML classifier for a specified indication or all inds (to benchmark)
        predict (used w/ 'effect=' - indication or ADR) is a list of compounds to classify with the trained ML model
        out=X saves benchmark SUMMARY->SUMMARY_ml_X; raw results->raw_results/raw_results_ml_X (same for RAN)
        currently supports random forest ('rf'), support vector machine ('svm'), 1-class SVM ('1csvm'), and logistic
        regression ('log') models are trained with leave-one-out cross validation during benchmarking

        @param method str: type of machine learning algorithm to use ('rf', 'svm', '1csvm', and 'log')
        @param effect Indication or ADR: provide a specific Indication or ADR object to train a classifer
        @param benchmark bool: benchmark the ML pipeline by training a classifier with LOOCV for each Indication or ADR
        @param adrs bool: if the models are trained with ADRs instead of Indications
        @param predict list: provide a list of Compound objects to classify with the model (only used in
        combination with effect=Indication/ADR object)
        @param seed int: choose a seed for reproducibility
        @param out str: file name extension for the output of benchmark (note: must have benchmark=True)
        """
        if out:
            if not os.path.exists('./raw_results/'):
                os.system('mkdir raw_results')
            if not os.path.exists('./results_analysed_named/'):
                os.system('mkdir results_analysed_named')

        paired_negs = {}

        # gather approved compound signatures for training
        def split_cs(efct, cmpd=None):
            mtrx = []
            for cm in efct.compounds:
                if cmpd:
                    if cm.id_ == cmpd.id_:
                        continue
                if self.indication_proteins:
                    if len(efct.proteins) >= 3:
                        eps = []
                        for ep in efct.proteins:
                            ep_index = self.protein_id_to_index[ep.id_]
                            eps.append(cm.sig[ep_index])
                        mtrx.append(eps)
                else:
                    mtrx.append(cm.sig)
            return mtrx, [1] * len(mtrx)

        def choose_negatives(efct, neg_set=negative, s=None, hold_out=None, avoid=[], test=None):
            if neg_set == 'inverse':
                if not self.compute_distance and not self.read_rmsds:
                    print('Please compute all compound-compound distances before using inverse_negatives().\n'
                          'Re-run with "compute_distance=True" or read in pre-computed distance file "read_rmsds="'
                          'in the CANDO object instantiation.')
            negatives = []
            used = avoid

            def pick_first_last(cmpd, s):

                def return_id(cm):
                    return cm[0].id_

                if neg_set == 'inverse':
                    r = int(len(self.compounds) / 2)
                    shuffled = list(map(return_id, cmpd.similar[::-1][0:r]))
                else:
                    shuffled = list(map(return_id, cmpd.similar))
                if s:
                    random.seed(s)
                    random.shuffle(shuffled)
                else:
                    s = random.randint(0, len(self.compounds) - 1)
                    random.seed(s)
                    random.shuffle(shuffled)
                for si in range(len(shuffled)):
                    n = shuffled[si]
                    if n in used:
                        continue
                    inv = self.get_compound(id_=n)
                    if inv not in efct.compounds:
                        if n not in used:
                            paired_negs[cmpd] = inv
                            return inv

            if test:
                inv = pick_first_last(c, s)
                return inv

            for ce in efct.compounds:
                if hold_out:
                    if ce.id_ == hold_out.id_:
                        continue
                inv = pick_first_last(ce, s)
                if self.indication_proteins:
                    if len(efct.proteins) >= 3:
                        eps = []
                        for ep in efct.proteins:
                            ep_index = self.protein_id_to_index[ep.id_]
                            eps.append(inv.sig[ep_index])
                        negatives.append(eps)
                else:
                    negatives.append(inv.sig)
                used.append(inv.id_)
            return negatives, [0] * len(negatives), used

        def model(meth, samples, labels, params=None, seed=None):
            if meth == 'rf':
                m = RandomForestClassifier(n_estimators=100, random_state=seed)
                m.fit(samples, labels)
                return m
            elif meth == 'svm':
                m = svm.SVC(kernel='rbf', gamma='scale', degree=3, random_state=seed)
                m.fit(samples, labels)
                return m
            elif meth == '1csvm':
                keep = []
                for i in range(len(samples)):
                    if labels[i] == 1:
                        keep.append(samples[i])
                m = svm.OneClassSVM(kernel='poly', gamma='scale', degree=2)
                m.fit(keep)
                return m
            elif meth == 'log':
                m = LogisticRegression(penalty='l2', solver='newton-cg', random_state=seed)
                m.fit(samples, labels)
                return m
            else:
                print("Please enter valid machine learning method ('rf', '1csvm', 'log', or 'svm')")
                quit()

        if benchmark:
            if adrs:
                effects = sorted(self.adrs, key=lambda x: (len(x.compounds), x.id_))[::-1]
            else:
                effects = sorted(self.indications, key=lambda x: (len(x.compounds), x.id_))[::-1]
            if out:
                frr = open('./raw_results/raw_results_ml_{}'.format(out), 'w')
                frr.write('Compound,Effect,Prob,Neg,Neg_prob\n')
                fran = open('./results_analysed_named/results_analysed_named_ml_{}'.format(out), 'w')
                fsum = open('summary_ml_{}'.format(out), 'w')
        else:
            if len(effect.compounds) < 1:
                print('No compounds associated with {} ({}), quitting.'.format(effect.name, effect.id_))
                quit()
            elif self.indication_proteins and len(effect.proteins) <= 2:
                print('Less than 3 proteins associated with {} ({}), quitting.'.format(effect.name, effect.id_))
            effects = [effect]

        rf_scores = []
        for e in effects:
            if len(e.compounds) < 2:
                continue
            if self.indication_proteins:
                if not len(e.proteins) >= 3:
                    continue
            tp_fn = [0, 0]
            fp_tn = [0, 0]
            for c in e.compounds:
                pos = split_cs(e, cmpd=c)
                negs = choose_negatives(e, s=seed, hold_out=c, avoid=[])
                already_used = negs[2]
                train_samples = np.array(pos[0] + negs[0])
                train_labels = np.array(pos[1] + negs[1])
                mdl = model(method, train_samples, train_labels, seed=seed)
                test_neg = choose_negatives(e, s=seed, avoid=already_used, test=c)
                if self.indication_proteins:
                    eps_pos = []
                    eps_neg = []
                    for ep in e.proteins:
                        ep_index = self.protein_id_to_index[ep.id_]
                        eps_pos.append(c.sig[ep_index])
                        eps_neg.append(test_neg.sig[ep_index])
                    pred = mdl.predict_proba(np.array([eps_pos]))
                    pred_neg = mdl.predict_proba(np.array([eps_neg]))
                else:
                    pred = mdl.predict_proba(np.array([c.sig]))
                    pred_neg = mdl.predict_proba(np.array([test_neg.sig]))
                pos_class = list(mdl.classes_).index(1)

                if pred[0][pos_class] > threshold:
                    tp_fn[0] += 1
                else:
                    tp_fn[1] += 1
                if pred_neg[0][pos_class] > threshold:
                    fp_tn[0] += 1
                else:
                    fp_tn[1] += 1
                if benchmark and out:
                    frr.write('{},{},{},{},{}\n'.format(c.id_, e.id_, pred[0][pos_class],
                                                        test_neg.id_, pred_neg[0][pos_class]))

            # predict whether query drugs are associated with this indication
            if predict:
                print('Indication: {}'.format(e.name))
                print('Leave-one-out cross validation: TP={}, FP={}, FN={}, TN={}, Acc={:0.3f}'.format(
                    tp_fn[0], fp_tn[0], tp_fn[1], fp_tn[1], 100 * ((tp_fn[0]+fp_tn[1]) / (float(len(e.compounds))*2))))
                negs = choose_negatives(e, s=seed)
                pos = split_cs(e)
                train_samples = np.array(pos[0] + negs[0])
                train_labels = np.array(pos[1] + negs[1])
                mdl = model(method, train_samples, train_labels, seed=seed)
                print('\tCompound\tProb')
                for c in predict:
                    inv = choose_negatives(effect, s=seed, test=c, avoid=negs[2])
                    if self.indication_proteins:
                        eps_pos = []
                        eps_neg = []
                        for ep in e.proteins:
                            ep_index = self.protein_id_to_index[ep.id_]
                            eps_pos.append(c.sig[ep_index])
                            eps_neg.append(test_neg.sig[ep_index])
                        pred = mdl.predict_proba(np.array([eps_pos]))
                        pred_neg = mdl.predict_proba(np.array([test_neg.sig]))
                    else:
                        pred = mdl.predict_proba(np.array([c.sig]))
                        pred_inv = mdl.predict_proba(np.array([inv.sig]))
                    pos_class = list(mdl.classes_).index(1)

                    print('\t{}\t{:0.3f}'.format(c.name, pred[0][pos_class]))
                    #print('\t{}\t{:0.3f}\t(random negative of {})'.format(inv.name, pred_inv[0][pos_class], c.name))

            # append loocv results to combined list
            rf_scores.append((e, tp_fn, fp_tn))

        sm = [0, 0, 0, 0]
        if benchmark:
            for rf_score in rf_scores:
                efct = rf_score[0]
                tfp = rf_score[1]
                ffp = rf_score[2]
                acc = (tfp[0] + ffp[1]) / (float(len(efct.compounds) * 2))
                sm[0] += len(efct.compounds)
                sm[1] += acc
                sm[2] += (acc * len(efct.compounds))
                if acc > 0.5:
                    sm[3] += 1
                if out:
                    fran.write('{}\t{}\t{}\t{}\t{:0.3f}\t{}\n'.format(efct.id_, len(efct.compounds),
                                                                      tfp[0], tfp[1], 100 * acc, efct.name))
            if out:
                fsum.write('aia\t{:0.3f}\n'.format(100 * (sm[1]/len(rf_scores))))
                fsum.write('apa\t{:0.3f}\n'.format(100 * (sm[2] / sm[0])))
                fsum.write('ic\t{}\n'.format(sm[3]))

            print('aia\t{:0.3f}'.format(100 * (sm[1]/len(rf_scores))))
            print('apa\t{:0.3f}'.format(100 * (sm[2] / sm[0])))
            print('ic\t{}'.format(sm[3]))
        return

    def raw_results_roc(self, rr_files, labels, save='roc-raw_results.pdf'):

        if len(labels) != len(rr_files):
            print('Please enter a label for each input raw results file '
                  '({} files, {} labels).'.format(len(rr_files), len(labels)))
            quit()

        n_per_d = {}
        dt = {}
        ds = {}
        metrics = {}
        truth = []
        scores = []
        for rr_file in rr_files:
            for l in open(rr_file, 'r').readlines()[1:]:
                ls = l.strip().split(',')
                pp = float(ls[2])
                truth.append(1)
                scores.append(pp)

                np = float(ls[4])
                truth.append(0)
                scores.append(np)
                if ls[1] not in n_per_d:
                    n_per_d[ls[1]] = 1
                else:
                    n_per_d[ls[1]] += 1
            pr = average_precision_score(truth, scores)
            fpr, tpr, thrs = roc_curve(truth, scores)
            area = roc_auc_score(truth, scores)
            dt[rr_file] = truth
            ds[rr_file] = scores
            metrics[rr_file] = [fpr, tpr, thrs, area, pr]

        plt.figure()
        lw = 2
        for rr_file in rr_files:
            i = rr_files.index(rr_file)
            [fpr, tpr, thrs, area, pr] = metrics[rr_file]
            plt.plot(fpr, tpr, lw=lw, label='{} (AUC-ROC={}, AUPR={})'.format(labels[i], format(area, '.3f'),
                                                                                         format(pr, '.3f')))
        plt.plot([0, 1], [0, 1], lw=lw, linestyle='--')
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel('False Positive Rate')
        plt.ylabel('True Positive Rate')
        plt.legend(loc="lower right", prop={'size': 8})
        if save:
            plt.savefig(save, dpi=300)
        plt.show()

    def canpredict_compounds(self, ind_id, n=10, topX=10, sum_scores=False, threshold=0.0,
                             keep_approved=False, associated=False, save=''):
        """!
        This function is used for predicting putative therapeutics for an indication
        of interest. Input an ind_id id and for each of the associated compounds, it will
        generate the similar compounds (based on distance) and add them to a dictionary
        with a value of how many times it shows up (enrichment). If a
        compound not approved for the indication of interest keeps showing
        up, that means it is similar in signature to the drugs that are
        ALREADY approved for the indication, so it may be a target for repurposing.
        Control how many similar compounds to consider with the argument 'n'.
        Use ind_id=None to find greatest score sum across all proteins (sum_scores must be >0.0)
        
        @param ind_id str: Indication id
        @param n int: top number of similar Compounds to be used for each Compound associated with the given Indication
        @param topX int: top number of predicted Compounds to be printed
        @param sum_scores bool: Sum all interaction scores across all proteins
        @param threshold float: a interaction score cutoff to use (ignores values for sum less than threshold)
        @param keep_approved bool: Print Compounds that are already approved for the Indication
        @param associated bool: Only print compounds with at least one associated disease ("repurposing" candidates)
        @param save str: name of a file to save results
        """
        if ind_id:
            i = self.indication_ids.index(ind_id)
            ind = self.indications[i]
            print("{0} compounds found for {1} --> {2}".format(len(ind.compounds), ind.id_, ind.name))
        else:
            print("Finding compounds with greatest summed scores in {}...".format(self.matrix))

        if not sum_scores:
            if self.pathways:
                if self.indication_pathways:
                    self.quantify_pathways(ind)
                else:
                    self.quantify_pathways()
            for c in ind.compounds:
                if c.similar_computed:
                    continue
                if self.pathways:
                    self.generate_similar_sigs(c, aux=True, sort=True)
                elif self.indication_proteins:
                    self.generate_similar_sigs(c, sort=True, proteins=ind.proteins)
                else:
                    self.generate_similar_sigs(c, sort=True)
        if not sum_scores:
            print("Generating compound predictions using top{} most similar compounds...\n".format(n))
            c_dct = {}
            for c in ind.compounds:
                for c2_i in range(n):
                    c2 = c.similar[c2_i]
                    if c2[1] == 0.0:
                        continue
                    already_approved = ind in c2[0].indications
                    k = c2[0].id_
                    if k not in c_dct:
                        c_dct[k] = [1, already_approved, c2_i]
                    else:
                        c_dct[k][0] += 1
                        c_dct[k][2] += c2_i
        else:
            c_dct = {}
            if self.indication_proteins and ind_id:
                indices = []
                for p in ind.proteins:
                    indices.append(self.protein_id_to_index[p.id_])
            else:
                indices = range(len(self.proteins))
            for c in self.compounds:
                ss = 0.0
                count = 0
                for pi in indices:
                    si = c.sig[pi]
                    if si >= threshold:
                        ss += c.sig[pi]
                        count += 1
                if ind_id:
                    already_approved = ind in c.indications
                else:
                    already_approved = False  # Not relevant since there is no indication
                c_dct[c.id_] = [ss, count, already_approved]
        if sum_scores:
            sorted_x = sorted(c_dct.items(), key=lambda x: (x[1][0], x[1][1]))[::-1]
        else:
            sorted_x = sorted(c_dct.items(), key=lambda x: (x[1][0], (-1 * (x[1][2] / x[1][0]))))[::-1]

        if save:
            fo = open(save, 'w')
            header = 1
        print("Printing the {} highest predicted compounds...\n".format(topX))
        if sum_scores:
            i = 0
            if keep_approved:
                print('rank\tscore\tsum\tapproved\tid\tname')
            else:
                print('rank\tscore\tsum\tid\tname')
            for p in enumerate(sorted_x):
                if i >= topX != -1:
                    break
                else:
                    co = self.get_compound(p[1][0])
                    if (associated and len(co.indications) > 0) or (not associated):
                        if keep_approved:
                            st = "{}\t{}\t{}\t{}\t{}\t{}".format(i + 1, p[1][1][1], round(p[1][1][0], 3),  p[1][1][2],
                                              co.id_, co.name)
                            print(st)
                            i += 1
                            if save:
                                if header:
                                    fo.write('rank\tscore\tsum\tapproved\tid\tname\n')
                                    header = 0
                                fo.write(st + '\n')
                        else:
                            st = "{}\t{}\t{}\t{}\t{}".format(i + 1, round(p[1][1][0], 2), p[1][1][1],
                                                              co.id_, co.name)
                            print(st)
                            i += 1
                            if save:
                                if header:
                                    fo.write('rank\tscore\tsum\tid\tname\n')
                                    header = 0
                                fo.write(st + '\n')
            return
        if not keep_approved:
            i = 0
            print('rank\tscore\tavg_r\tid\tname')
            for p in enumerate(sorted_x):
                if i >= topX != -1:
                    break
                co = self.get_compound(p[1][0])
                if (associated and len(co.indications) > 0) or (not associated):
                    if p[1][1][1]:
                        continue
                    else:
                        st = "{}\t{}\t{}\t{}\t{}".format(i + 1, p[1][1][0], round(p[1][1][2]/p[1][1][0], 1),
                                                      self.get_compound(p[1][0]).id_, self.get_compound(p[1][0]).name)
                        print(st)
                        i += 1
                        if save:
                            if header:
                                fo.write('rank\tscore\tavg_r\tid\tname\n')
                                header = 0
                            fo.write(st + '\n')
        else:
            i = 0
            print('rank\tscore\tavg_r\tapproved\tid\tname')
            for p in enumerate(sorted_x):
                if i >= topX != -1:
                    break
                co = self.get_compound(p[1][0])
                if (associated and len(co.indications) > 0) or (not associated):
                    st = "{}\t{}\t{}\t{}\t{}\t{}".format(i + 1, p[1][1][0], round(p[1][1][2] / p[1][1][0], 1),p[1][1][1],
                                                    self.get_compound(p[1][0]).id_, self.get_compound(p[1][0]).name)
                    print(st)
                    i += 1
                    if save:
                        if header:
                            fo.write('rank\tscore\tavg_r\tapproved\tid\tname\n')
                            header = 0
                        fo.write(st + '\n')
        print('\n')

    def canpredict_indications(self, new_sig=None, new_name=None, cando_cmpd=None, n=10, topX=10):
        """!
        This function is the inverse of canpredict_compounds. Input a compound
        of interest cando_cmpd (or a novel protein signature of interest new_sig)
        and the most similar compounds to it will be computed. The indications
        associated with the top n most similar compounds to the query compound will
        be examined to see if any are repeatedly enriched.
        
        @param new_sig str: Path to the new Compound signature
        @param new_name str: Name to be used for the new Compound
        @param cando_cmpd Compound: Compound object to be used
        @param n int: top number of similar Compounds to be used for prediction
        @param topX int: top number of predicted Indications to be printed
        """
        if new_sig:
            cmpd = self.add_cmpd(new_sig, new_name)
        elif cando_cmpd:
            cmpd = cando_cmpd
            print("Using CANDO compound {}".format(cmpd.name))
            print("Compound has id {} and index {}".format(cmpd.id_, cmpd.index))
        print("Comparing signature to all CANDO compound signatures...")
        self.generate_similar_sigs(cmpd, sort=True)
        print("Generating indication predictions using top{} most similar compounds...".format(n))
        i_dct = {}
        for c in cmpd.similar[0:n]:
            for ind in c[0].indications:
                if ind.id_ not in i_dct:
                    i_dct[ind.id_] = 1
                else:
                    i_dct[ind.id_] += 1
        sorted_x = sorted(i_dct.items(), key=operator.itemgetter(1), reverse=True)
        print("Printing the {} highest predicted indications...\n".format(topX))
        print("rank\tscore\tind_id    \tindication")
        for i in range(topX):
            indd = self.get_indication(sorted_x[i][0])
            print("{}\t{}\t{}\t{}".format(i+1, sorted_x[i][1], indd.id_, indd.name))
        print('')

    def similar_compounds(self, new_sig=None, new_name=None, cando_cmpd=None, n=10):
        """!
        Computes and prints the top n most similar compounds to an input
        Compound object cando_cmpd or input novel signature new_sig

        @param new_sig list: List float of novel compound protein interaction signature
        @param new_name str: Drug name
        @param cando_cmpd Compound: Compound object
        @param n int: top number of similar Compounds to be used for prediction
        """
        if new_sig:
            cmpd = self.add_cmpd(new_sig, new_name)
        elif cando_cmpd:
            cmpd = cando_cmpd
            print("Using CANDO compound {}".format(cmpd.name))
            print("Compound has id {} and index {}".format(cmpd.id_, cmpd.index))
        print("Comparing signature to all CANDO compound signatures...")
        self.generate_similar_sigs(cmpd, sort=True)
        print("Printing top{} most similar compounds...\n".format(n))
        print("rank\tdist\tid\tname")
        for i in range(n+1):
            print("{}\t{:.3f}\t{}\t{}".format(i+1, cmpd.similar[i][1], cmpd.similar[i][0].id_, cmpd.similar[i][0].name))
        print('\n')
        return cmpd.similar

    def add_cmpd(self, new_sig, new_name):
        """!
        Add a new Compound object to the platform
        
        @param new_sig str: Path to the tab-separated interaction scores
        @param new_name str: Name for the new Compound
        @return cmpd Compound: Compound object
        """
        with open(new_sig, 'r') as nsf:
            n_sig = [0.00] * len(self.proteins)
            for l in nsf:
                [pr, sc] = l.strip().split('\t')
                pr_i = self.protein_id_to_index[pr]
                n_sig[pr_i] = sc
        #new_sig = pd.read_csv(new_sig, sep='\t', index_col=0, header=None)
        #if not new_name:
        #    print("Compound needs a name. Set 'new_name'")
        #    return
        i = len(self.compounds)
        cmpd = Compound(new_name, i, i)
        cmpd.sig = n_sig
        #cmpd.sig = new_sig[[1]].T.values[0].tolist()
        self.compounds.append(cmpd)
        print("New compound is " + cmpd.name)
        print("New compound has id {} and index {}".format(cmpd.id_, cmpd.index))
        return cmpd

    def sigs(self, rm):
        """!
        Return a list of all signatures, rm is a list of compound ids you do not want in the list

        @param rm list: List of compound ids to remove from list of signatures
        @return list: List of all signatures
        """
        return [x.sig for x in self.proteins if x.id_ not in rm]

    def save_rmsds_to_file(self, f):
        """!
        Write calculated distances of all compounds to all compounds to file

        @param f File name to save distances
        """
        def rmsds_to_str(cmpd):
            o = ''
            for s in cmpd.similar:
                o += '{}\t'.format(s[1])
            o = o + '\n'
            return o

        with open(f, 'w') as srf:
            for c in self.compounds:
                srf.write(rmsds_to_str(c))

    def fusion(self, cando_objs, out_file='', method='sum'):
        """!
        This function re-ranks the compounds according to the desired comparison specified by
        'method' -> currently supports 'min', 'avg', 'mult', and 'sum'

        @param cando_objs list: List of CANDO objects
        @param out_file str: Path to where the result will be written
        @param method str: Method of fusion to be used (e.g., sum, mult, etc.)
        """
        print("Fusing CANDO objects using " + method)
        cnd = CANDO(self.c_map, self.i_map)
        if self.rm_cmpds:
            cnd.compounds = self.compounds
            cnd.indications = self.indications
            for c in cnd.compounds:
                c.similar = []
                c.sig = []
        dn = [self.data_name]
        for obj in cando_objs:
            dn.append(obj.data_name)
        cnd.data_name = "-".join(dn) + '-' + method
        cid_to_ranks = {}
        for c in self.compounds:
            cid_to_ranks[c.id_] = {}
            sims = c.similar
            for i in range(len(sims)):
                cid_to_ranks[c.id_][sims[i][0].id_] = [i]
        for cando_obj in cando_objs:
            for c2 in cando_obj.compounds:
                sims2 = c2.similar
                for j in range(len(sims2)):
                    cid_to_ranks[c2.id_][sims2[j][0].id_].append(j)
        for c3 in cnd.compounds:
            ranks_dct = cid_to_ranks[c3.id_]
            for c4 in cnd.compounds:
                if c4.id_ == c3.id_:
                    continue
                ranks = ranks_dct[c4.id_]
                if method == 'min':
                    c3.similar.append((c4, float(min(ranks))))
                if method == 'sum':
                    c3.similar.append((c4, float(sum(ranks))))
                if method == 'avg':
                    c3.similar.append((c4, (float(sum(ranks))) / len(ranks)))
                if method == 'mult':
                    m = 1.0
                    for r in ranks:
                        m *= r
                    c3.similar.append((c4, m))
        if out_file:
            with open(out_file, 'w') as fo:
                for co in cnd.compounds:
                    s = list(map(str, [x[1] for x in co.similar]))
                    fo.write('\t'.join(s) + '\n')
        for cf in cnd.compounds:
            sorted_scores = sorted(cf.similar, key=lambda x: x[1] if not math.isnan(x[1]) else 100000)
            cf.similar = sorted_scores
            cf.similar_computed = True
            cf.similar_sorted = True
        return cnd

    def normalize(self):
        """!
        Normalize the distance scores to between [0,1]. Simply divides all scores by the largest distance
        between any two compounds.

        """
        if len(self.compounds[0].similar) == 0:
            print('Similar scores not computed yet -- quitting')
            return

        mx = 0
        for c in self.compounds:
            for s in c.similar:
                if s[1] > mx:
                    mx = s[1]

        print('Max value is {}'.format(mx))

        def norm(x):
            v = x[1] / mx
            return x[0], v

        for c in self.compounds:
            c.similar = list(map(norm, c.similar))
        return

    def __str__(self):
        """!
        Print stats about the CANDO object

        """
        nc = len(self.compounds)
        b = self.compounds[0].similar_computed
        ni = len(self.indications)
        np = len(self.proteins)
        if np:
            return 'CANDO: {0} compounds, {1} proteins, {2} indications\n' \
                   '\tMatrix - {3}\nIndication mapping - {4}\n' \
                   '\tDistances computed - {5}'.format(nc, np, ni, self.matrix, self.i_map, b)
        elif self.read_rmsds:
            return 'CANDO: {0} compounds, {1} indications\n' \
                   '\tCompound comparison file - {2}\n' \
                   '\tIndication mapping - {3}'.format(nc, ni, self.read_rmsds, self.i_map)
        else:
            return 'CANDO: {0} compounds, {1} indications\n' \
                   '\tIndication mapping - {2}'.format(nc, ni, self.i_map)


class Matrix(object):
    """!
    An object to represent a matrix

    Intended for easier handling of matrices.
    Convert between fpt and tsv, as well as distance to similarity (and vice versa)
    """
    def __init__(self, matrix_file, rmsd=False, convert_to_tsv=False):
        ## @var matrix_file
        # str: Path to file with interaction scores
        self.matrix_file = matrix_file
        ## @var rmsd
        # bool: if the matrix_file is an rmsd file
        self.rmsd = rmsd
        ## @var convert_to_tsv
        # bool: Convert old matrix format (.fpt) to .tsv
        self.convert_to_tsv = convert_to_tsv
        ## @var proteins
        # list: Proteins in the Matrix
        self.proteins = []
        ## @var values
        # list: Values in the Matrix
        self.values = []

        def pro_name(l):
            name = l[0]
            curr = l[1]
            index = 1
            while curr != ' ':
                name += curr
                index += 1
                curr = l[index]
            return name

        if not rmsd:
            with open(matrix_file, 'r') as f:
                lines = f.readlines()
                if convert_to_tsv:
                    if matrix_file[-4:] == '.fpt':
                        out_file = '.'.join(matrix_file.split('.')[:-1]) + '.tsv'
                    else:
                        out_file = matrix_file + '.tsv'
                    of = open(out_file, 'w')
                    for l_i in range(len(lines)):
                        name = pro_name(lines[l_i])
                        scores = []
                        i = 24
                        while i < len(lines[l_i]):
                            score = lines[l_i][i:i + 5]
                            i += 8
                            scores.append(score)
                        self.proteins.append(name)
                        self.values.append(list(map(float, scores)))
                        of.write("{0}\t{1}\n".format(name, '\t'.join(scores)))
                    of.close()
                else:
                    for l_i in range(len(lines)):
                        vec = lines[l_i].strip().split('\t')
                        if len(vec) < 2:
                            print('The matrix file {} is in the old fpt format -- please '
                                  'convert to tsv with the following line of code:'.format(self.matrix_file))
                            print('-> Matrix("{}", convert_to_tsv=True) <-'.format(self.matrix_file))
                            quit()
                        name = vec[0]
                        scores = vec[1:]
                        self.proteins.append(name)
                        self.values.append(list(map(float, scores)))
        else:
            with open(matrix_file, 'r') as rrs:
                lines = rrs.readlines()
                for i in range(len(lines)):
                    scores = list(map(float, lines[i].strip().split('\t')))
                    self.values.append(scores)

    def convert(self, out_file):
        """!
        Convert similarity matrix to distance matrix or vice versa. The
        first value in the matrix will determine the type of conversion
        (0.0 means distance to similarity, 1.0 means similarity to distance).

        @param out_file str: File path to which write the converted matrix.
        """
        if self.values[0][0] == 0.0:
            metric = 'd'
        elif self.values[0][0] == 1.0:
            metric = 's'
        else:
            metric = None
            print('The first value is not 0.0 or 1.0; '
                  'please ensure the matrix is generated properly')
            quit()

        def to_dist(s):
            return 1 - s

        def to_sim(d):
            return 1 / (1 + d)

        of = open(out_file, 'w')
        if metric == 'd':
            for vs in self.values:
                vs = list(map(to_sim, vs))
                of.write("{}\n".format('\t'.join(list(map(str, vs)))))
        else:
            if metric == 's':
                for vs in self.values:
                    vs = list(map(to_dist, vs))
                    of.write("{}\n".format('\t'.join(list(map(str, vs)))))
        of.close()

    def normalize(self, outfile, dimension='drugs', method='avg'):
        """!
        Normalize the interaction scores across drugs (default) or proteins (not implemented yet).

        @param outfile str: File path to which is written the converted matrix.
        @param dimension str: which vector to normalize - either 'drugs' to normalize all
        scores within the proteomic vector or 'proteins' to normalize for a protein against
        all drug scores.
        @param method str: normalize by the average or max within the vectors
        """
        # dimensions include drugs or features (e.g. "proteins")
        # methods are average ('avg') or max ('max')
        dvs = {}  # drug vectors
        cc = 0
        if dimension == 'drugs':
            for vec in self.values:
                for vi in range(len(vec)):
                    if cc == 0:
                        dvs[vi] = []
                    dvs[vi].append(vec[vi])
                cc += 1

        new_dvecs = []
        for i in range(len(dvs)):
            vec = dvs[i]
            if method == 'avg':
                norm_val = np.average(vec)
            elif method == 'max':
                norm_val = max(vec)
            else:
                print('Please enter a proper normalization method: "max" or "avg"')
                quit()

            def norm(x):
                if norm_val == 0:
                    return 0.0
                else:
                    return x/norm_val

            new_dvecs.append(list(map(norm, vec)))

        pvs = {}
        for dvi in range(len(new_dvecs)):
            for p in range(len(self.proteins)):
                try:
                    pvs[p].append(new_dvecs[dvi][p])
                except KeyError:
                    pvs[p] = [new_dvecs[dvi][p]]

        with open(outfile, 'w') as fo:
            for p in range(len(self.proteins)):
                fo.write('{}\t{}\n'.format(self.proteins[p], '\t'.join(list(map(str, pvs[p])))))


def generate_matrix(cmpd_scores='', prot_scores='', matrix_file='cando_interaction_matrix.tsv', ncpus=1):
    """!
    Generate a CANDO Matrix 

    @param cmpd_scores str: File path to tab-separated scores for all Compounds
    @param prot_scores str: File path to tab-separated scores for all Proteins
    @param matrix_file str: File path to where the generated Matrix will be written
    @param ncpus int: Number of cpus to use for parallelization
    """
    def print_time(s):
        if s >= 60:
            m = s / 60.0
            s -= m * 60.0
            if m >= 60.0:
                h = m / 60.0
                m -= h * 60.0
                print("Matrix generation took {:.0f} hr {:.0f} min {:.0f} s to finish.".format(h, m, s))
            else:
                print("Matrix generation took {:.0f} min {:.0f} s to finish.".format(m, s))
        else:
            print("Matrix generation took {:.0f} s to finish.".format(s))

    start = time.time()

    print("Compiling compound scores...")
    c_scores = pd.read_csv(cmpd_scores, sep='\t', index_col=0)

    print("Compiling binding site scores...")
    p_scores = pd.read_csv(prot_scores, sep='\t', index_col=0, header=None)

    print("Calculating interaction scores...")
    pool = mp.Pool(ncpus)
    scores_temp = pool.starmap_async(get_scores,
                                     [(int(c), p_scores, c_scores.loc[:, c]) for c in c_scores.columns]).get()
    pool.close()
    first = True
    scores = pd.DataFrame()
    print("Generating matrix...")
    for i in scores_temp:
        if first:
            scores = pd.DataFrame(i)
            first = False
        else:
            scores = scores.join(pd.DataFrame(i))
    scores.rename(index=dict(zip(range(len(p_scores.index)), p_scores.index)), inplace=True)
    scores.to_csv(matrix_file, sep='\t', header=None, float_format='%.3f')

    end = time.time()
    print("Matrix written to {}.".format(matrix_file))
    print_time(end-start)


def generate_scores(fp="rd_ecfp4", cmpd_pdb='', out_path='.'):
    """!
    Generate the fingerprint for a new compound and calculate the Tanimoto
    similarities against all binding site ligands.
    
    @param fp str: The fingerprinting software and method used, e.g. 'rd_ecfp4', 'ob_fp2'
    @param cmpd_pdb str: File path to the PDB
    @param out_path str: Path to where the scores file will be written
    """
    fp_name = fp
    fp = fp.split("_")
    # Check for correct fingerprinting method
    if fp[0] not in ['rd', 'ob']:
        print("{} is not a correct fingerprinting method.".format(fp_name))
    else: 
        if fp[0] == 'ob' and fp[1] not in ['fp4', 'fp2']:
            print("{} is not a correct fingerprinting method.".format(fp_name))
        elif fp[0] == 'rd' and fp[1] not in ['daylight', 'ecfp4']:
            print("{} is not a correct fingerprinting method.".format(fp_name))

    # Pull and read in fingerprints for ligands
    get_fp_lig(fp_name)
    pre = os.path.dirname(__file__)
    bs = pd.read_csv("{}/v2.0/ligands_fps/{}.tsv".format(pre, fp_name), sep='\t', header=None, index_col=0)
    bs = bs.replace(np.nan, '', regex=True)
    sites = bs.index
    print("Generating {} fingerprints and scores...".format('_'.join(fp)))
    if cmpd_pdb != '':
        cmpd_name = cmpd_pdb.split('/')[-1].split('.')[0]
        try:
            cmpd_id = int(cmpd_name)
        except ValueError:
            cmpd_id = 10000
        out_name = "{}_scores.tsv".format(cmpd_id)
        scores = [score_fp(fp, cmpd_pdb, cmpd_id, bs)]
    else:
        print("cmpd_pdb is empty. Need a PDB file.")
        return
    cmpd_scores = pd.DataFrame(index=sites)
    cmpd_scores = cmpd_scores.T
    for i in scores:
        for key, value in i.items():
            temp = pd.DataFrame({key: value}, index=sites)
            cmpd_scores = cmpd_scores.append(temp.T)
    cmpd_scores = cmpd_scores.T

    if not os.path.exists('{}/{}'.format(out_path, fp_name)):
        os.makedirs('{}/{}'.format(out_path, fp_name))

    cmpd_scores.to_csv('{}/{}/{}'.format(out_path, fp_name, out_name), index=True,
                       header=True, sep='\t', float_format='%.3f')
    print("Tanimoto scores written to {}/{}/{}\n".format(out_path, fp_name, out_name))


def generate_signature(cmpd_scores='', prot_scores='', matrix_file=''):
    """!
    Generate signature

    @param cmpd_scores str: File path to tab-separated scores for all Compounds
    @param prot_scores str: File path to tab-separated scores for all Proteins
    @param matrix_file str: File path to where the generated Compounds signature will be written
    """
    def print_time(s):
        if s >= 60:
            m = s / 60.0
            s -= m * 60.0
            if m >= 60.0:
                h = m / 60.0
                m -= h * 60.0
                print("Signature generation took {:.0f} hr {:.0f} min {:.0f} s to finish.".format(h, m, s))
            else:
                print("Signature generation took {:.0f} min {:.0f} s to finish.".format(m, s))
        else:
            print("Signature generation took {:.0f} s to finish.".format(s))

    if matrix_file == '':
        matrix_file = "{}_signature.tsv".format(cmpd_scores.split('/')[-1].split('.')[0].split('_')[0])
    start = time.time()
    
    print("Compiling compound scores...")
    c_scores = pd.read_csv(cmpd_scores, sep='\t', index_col=0)
    
    print("Compiling binding site scores...")
    p_scores = pd.read_csv(prot_scores, sep='\t', index_col=0, header=None)

    print("Generating interaction signature...")
    print(c_scores.columns[0])
    c = c_scores.columns[0]
    scores_temp = get_scores(c, p_scores, c_scores.loc[:, c])
    scores = pd.DataFrame(scores_temp)
    scores.rename(index=dict(zip(range(len(p_scores.index)), p_scores.index)), inplace=True)
    scores.to_csv(matrix_file, sep='\t', header=None, float_format='%.3f')

    end = time.time()
    print("Signature written to {}.".format(matrix_file))
    print_time(end-start)


def get_scores(c, p_scores, c_score):
    """!
    Get best score for each Compound-Protein interaction

    @param c int: Compound id
    @param p_scores df: DataFrame of all Protein ligands
    @param c_score df: DataFrame of all Compound-ligand scores
    """
    l = []
    for pdb in p_scores.index:
        temp_value = 0.000
        if pd.isnull(p_scores.loc[pdb][1]):
            l.append(temp_value)
            continue
        for bs in p_scores.loc[pdb][1].split(','):
            try:
                if temp_value < c_score[bs]:
                    temp_value = c_score[bs]
            except KeyError:
                continue
        l.append(temp_value)
    return {c: l}


def score_fp(fp, cmpd_file, cmpd_id, bs):
    """!
    Generate the scores for a given Compound against all Protein ligands.

    @param fp str: Fingerprinting software and method used, e.g., rd_ecfp4
    @param cmpd_file str: File path to PDB
    @param cmpd_id int: Number correspodning to the new Compound id
    @param bs df: DataFrame of all protein ligand fingerprints for the given fingerprinting method (fp)
    """
    l = []
    # Use RDkit
    if fp[0] == 'rd':
        try:
            cmpd = Chem.MolFromPDBFile(cmpd_file)
            # ECFP4 - extended connectivity fingerprint
            if fp[1] == 'ecfp4':
                cmpd_fp = AllChem.GetMorganFingerprintAsBitVect(cmpd, 2, nBits=1024)
            # Daylight
            elif fp[1] == 'daylight':
                cmpd_fp = rdmolops.RDKFingerprint(cmpd)
            else:
                l.append(0.000)
            bit_fp = DataStructs.BitVectToText(cmpd_fp)
        except:
            print ("Reading Exception: ", cmpd_id)
            for pdb in bs.index:
                l.append(0.000)
            return {cmpd_id: l}
        print("Calculating tanimoto scores for compound {} against all binding site ligands...".format(cmpd_id))
        for pdb in bs.index:
            if bs.loc[pdb][1] == '':
                l.append(0.000)
                continue
            try:
                # Tanimoto similarity
                score = tanimoto_sparse(bit_fp, str(bs.loc[pdb][1]))
                l.append(score)
            except:
                l.append(0.000)
                continue
    # Use OpenBabel
    elif fp[0] == 'ob':
        try:
            cmpd = next(pybel.readfile("pdb", cmpd_file))
            # FP2 - Daylight
            if fp[1] == 'fp2':
                cmpd_fp = cmpd.calcfp('fp2')
            # FP4 - SMARTS
            elif fp[1] == 'fp4':
                cmpd_fp = cmpd.calcfp('fp4')
        except:
            for pdb in bs.index:
                l.append(0.000)
            return {cmpd_id: l}

        bit_fp = cmpd_fp.bits
        print("Calculating tanimoto scores for {} against all binding site ligands...".format(cmpd_id))
        for pdb in bs.index:
            if bs.loc[pdb][1] == '':
                l.append(0.000)
                continue
            bs_fp = bs.loc[pdb][1].split(',')
            bs_fp = [int(bs_fp[x]) for x in range(len(bs_fp))]
            try:
                # Tanimoto similarity
                score = tanimoto_dense(bit_fp, bs_fp)
                l.append(score)
            except:
                l.append(0.000)
                continue
    return {cmpd_id: l}


def tanimoto_sparse(str1, str2):
    """!
    Calculate the tanimoto coefficient for a pair of sparse vectors

    @param str1 str: String of 1s and 0s representing the first compound fingerprint
    @param str2 str: String of 1s and 0s representing the second compound fingerprint
    """
    n_c = 0.0
    n_a = 0.0
    n_b = 0.0
    for i in range(len(str1)):
        if str1[i] == '1' and str2[i] == '1':
            n_c += 1
        if str1[i] == '1':
            n_a += 1
        if str2[i] == '1':
            n_b += 1
    if n_c + n_a + n_b == 0:
        return 0.000
    return float(n_c/(n_a+n_b-n_c))    


def tanimoto_dense(list1, list2):
    """!
    Calculate the tanimoto coefficient for a pair of dense vectors

    @param list1 list: List of positions that have a 1 in first compound fingerprint
    @param list2 list: List of positions that have a 1 in second compound fingerprint
    """
    c = [common_item for common_item in list1 if common_item in list2]
    return float(len(c))/(len(list1) + len(list2) - len(c))


def get_fp_lig(fp):
    """!
    Download precompiled binding site ligand fingerprints using the given fingerprint method.

    @param fp str: Fingerprinting method used to compile each binding site ligand fingerprint
    """
    pre = os.path.dirname(__file__)
    out_file = '{}/v2.0/ligands_fps/{}.tsv'.format(pre, fp)
    if not os.path.exists(out_file):
        print('Downloading ligand fingerprints for {}...'.format(fp))
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/ligands_fps/{}.tsv'.format(fp)
        dl_file(url, out_file)
        print("Ligand fingerprints downloaded.")


def get_v2(matrix='nrpdb'):
    """!
    Download CANDO v2.0 data.

    This data includes: 
        - Compound mapping (approved and all)
        - Indication-compound mapping
        - Scores file for all approved compounds (fingerprint: rd_ecfp4)
        - Matrix file for approved drugs (2,162) and all proteins (14,610) (fingerprint: rd_ecfp4)
    """
    print('Downloading data for v2...')
    # Dirs
    if not os.path.exists('v2.0'):
        os.mkdir('v2.0')
    if not os.path.exists('v2.0/mappings'):
        os.mkdir('v2.0/mappings')
    if not os.path.exists('v2.0/matrices'):
        os.mkdir('v2.0/matrices')
    if not os.path.exists('v2.0/prots'):
        os.mkdir('v2.0/prots')
    if not os.path.exists('v2.0/cmpds/'):
        os.mkdir('v2.0/cmpds')
    if not os.path.exists('v2.0/cmpds/scores'):
        os.mkdir('v2.0/cmpds/scores')
    # Mappings
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/mappings/drugbank-approved.tsv'
    dl_file(url, 'v2.0/mappings/drugbank-approved.tsv')
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/mappings/drugbank-all.tsv'
    dl_file(url, 'v2.0/mappings/drugbank-all.tsv')
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/mappings/ctd_2_drugbank.tsv'
    dl_file(url, 'v2.0/mappings/ctd_2_drugbank.tsv')
    # Matrices
    if matrix == 'all':
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/matrices/rd_ecfp4/drugbank-approved_x_nrpdb.tsv'
        dl_file(url, 'v2.0/matrices/rd_ecfp4/drugbank-approved_x_nrpdb.tsv')
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/matrices/ob_fp4/drugbank-approved_x_nrpdb.tsv'
        dl_file(url, 'v2.0/matrices/ob_fp4/drugbank-approved_x_nrpdb.tsv')
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/matrices/rd_ecfp4/drugbank-human.tsv'
        dl_file(url, 'v2.0/matrices/rd_ecfp4/drugbank-human.tsv')
    elif matrix == 'nrpdb':
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/matrices/rd_ecfp4/drugbank-approved_x_nrpdb.tsv'
        dl_file(url, 'v2.0/matrices/rd_ecfp4/drugbank-approved_x_nrpdb.tsv')
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/matrices/ob_fp4/drugbank-approved_x_nrpdb.tsv'
        dl_file(url, 'v2.0/matrices/ob_fp4/drugbank-approved_x_nrpdb.tsv')
    elif matrix == 'human':
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/matrices/rd_ecfp4/drugbank-human.tsv'
        dl_file(url, 'v2.0/matrices/rd_ecfp4/drugbank-human.tsv')
    # Proteins
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/prots/nrpdb.tsv'
    dl_file(url, 'v2.0/prots/nrpdb.tsv')
    # Compounds
    if not os.path.exists('v2.0/cmpds/scores/drugbank-approved-rd_ecfp4.tsv'):
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/cmpds/scores/drugbank-approved-rd_ecfp4.tsv.gz'
        dl_file(url, 'v2.0/cmpds/scores/drugbank-approved-rd_ecfp4.tsv.gz')
        os.chdir("v2.0/cmpds/scores")
        os.system("gunzip -f drugbank-approved-rd_ecfp4.tsv.gz")
        os.chdir("../../..")
    print('All data for v2.0 downloaded.')


def get_tutorial():
    """!
    Download data for tutorial.

    This data includes:
        - Example Matrix (Approved drugs (2,162) and 64 proteins)
        - v2.0 Compound mapping (approved and all)
        - v2.0 Indication - Compound mapping
        - Compound scores file for all approved compounds (fingerprint: rd_ecfp4)
        - Example Protein scores file (64 proteins) for all binding site ligands for each Protein (fingerprint: rd_ecfp4)
        - Example Compound in PDB format to generate a new fingerprint and vector in the Matrix
        - Example Pathways set
    """
    print('Downloading data for tutorial...')
    if not os.path.exists('examples'):
        os.mkdir('examples')
    # Example matrix (rd_ecfp4 w/ 64 prots x 2,162 drugs)
    if not os.path.exists('./examples/example-matrix.tsv'):
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/examples/example-matrix.tsv'
        dl_file(url, './examples/example-matrix.tsv')
    # Protein scores
    if not os.path.exists('./examples/example-prots_scores.tsv'):
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/examples/example-prots_scores.tsv'
        dl_file(url, './examples/example-prots_scores.tsv')

    if not os.path.exists('v2.0'):
        os.mkdir('v2.0')
    if not os.path.exists('v2.0/mappings'):
        os.mkdir('v2.0/mappings')
    # Compound mapping
    if not os.path.exists('v2.0/mappings/drugbank-approved.tsv'):
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/mappings/drugbank-approved.tsv'
        dl_file(url, 'v2.0/mappings/drugbank-approved.tsv')
    # Compound-indication mapping (CTD)
    if not os.path.exists('v2.0/mappings/ctd_2_drugbank.tsv'):
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/mappings/ctd_2_drugbank.tsv'
        dl_file(url, 'v2.0/mappings/ctd_2_drugbank.tsv')
    # Compounds scores
    if not os.path.exists('v2.0/cmpds/'):
        os.mkdir('v2.0/cmpds')
    if not os.path.exists('v2.0/cmpds/scores'):
        os.mkdir('v2.0/cmpds/scores')
    if not os.path.exists('v2.0/cmpds/scores/drugbank-approved-rd_ecfp4.tsv'):
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/cmpds/scores/drugbank-approved-rd_ecfp4.tsv.gz'
        dl_file(url, 'v2.0/cmpds/scores/drugbank-approved-rd_ecfp4.tsv.gz')
        os.chdir("v2.0/cmpds/scores")
        os.system("gunzip -f drugbank-approved-rd_ecfp4.tsv.gz")
        os.chdir("../../..")
    # New compound
    if not os.path.exists('./examples/8100.pdb'):
        url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/examples/8100.pdb'
        dl_file(url, './examples/8100.pdb')
    # Protein subset
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/examples/example-uniprot_set'
    dl_file(url, './examples/example-uniprot_set')
    print('All data for tutorial downloaded.')


def get_test():
    """!
    Download data for test script.

    This data includes:
        - Test Matrix (Approved drugs (2,162) and 64 proteins)
        - v2.0 Compound mapping (approved and all)
        - v2.0 Indication - Compound mapping
        - Compound scores file for all approved compounds (fingerprint: rd_ecfp4)
        - Test Protein scores file (64 proteins) for all binding site ligands for each Protein (fingerprint: rd_ecfp4)
        - Test Compound in PDB format to generate a new fingerprint and vector in the Matrix
        - Directory of test Compounds in PDB format to generate multiple new fingerprints and vectors in the Matrix
        - Test Pathways set
    """
    print('Downloading data for test...')
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/test/test-cmpd_scores.tsv'
    dl_file(url, 'test/test-cmpd_scores.tsv')
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/test/test-prot_scores.tsv'
    dl_file(url, 'test/test-prot_scores.tsv')
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/test/test-cmpds.tsv'
    dl_file(url, 'test/test-cmpds.tsv')
    with open('test/test-cmpds.tsv', 'r') as f:
        l = []
        for i in f:
            i = i.split('\t')[0]
            i = "{}.pdb".format(i)
            l.append(i)
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/test/test-cmpds_pdb'
    out = 'test/test-cmpds_pdb'
    dl_dir(url, out, l)
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/test/test-inds.tsv'
    dl_file(url, 'test/test-inds.tsv')
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/test/8100.pdb'
    dl_file(url, 'test/8100.pdb')
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/test/test-uniprot_set'
    dl_file(url, 'test/test-uniprot_set')
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/test/vina64x.fpt'
    dl_file(url, 'test/vina64x.fpt')
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/test/toy64x.fpt'
    dl_file(url, 'test/toy64x.fpt')
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/test/test-pathway-prot.tsv'
    dl_file(url, 'test/test-pathway-prot.tsv')
    url = 'http://protinfo.compbio.buffalo.edu/cando/data/v2/test/test-pathway-mesh.tsv'
    dl_file(url, 'test/test-pathway-mesh.tsv')
    print('All test data downloaded.\n')


def dl_dir(url, out, l):
    """!
    Function to recursively download a directory.

    Prints the name of the directory and a progress bar.

    @param url str: URL of the dir to be downloaded
    @param out str: Path to where the dir will be downloaded
    @param l list: List of files in dir to be downloaded
    """
    if not os.path.exists(out):
        os.makedirs(out)
    else:
        for n in l:
            if not os.path.exists("{}/{}".format(out, n)):
                break
        return
    format_custom_text = progressbar.FormatCustomText(
        '%(f)s',
        dict(
            f='',
        ),
    )
    widgets = [
        format_custom_text,
        ' [', progressbar.DataSize(format='%(scaled)i files',), '] ',
        progressbar.Bar(left='[', right=']'),
        ' [', progressbar.ETA(), '] ',
    ]
    num_bars = len(l)
    bar = progressbar.ProgressBar(max_value=num_bars, widgets=widgets).start()
    i = 0
    for n in l:
        format_custom_text.update_mapping(f=out)
        url2 = "{}/{}".format(url, n)
        r = requests.get(url2)
        out_file = "{}/{}".format(out, n)
        with open(out_file, 'wb') as f:
            f.write(r.content)
        bar.update(i)
        i += 1
    bar.finish()


def dl_file(url, out_file):
    """!
    Function to download a file.

    Prints the name of the file and a progress bar.

    @param url str: URL of the file to be downloaded
    @param out_file str: File path to where the file will be downloaded
    """
    if os.path.exists(out_file):
        return
    elif not os.path.exists(os.path.dirname(out_file)):
        os.makedirs(os.path.dirname(out_file))
    time.sleep(1)
    r = requests.get(url, stream=True)
    format_custom_text = progressbar.FormatCustomText(
        '%(f)s',
        dict(
            f='',
        ),
    )
    widgets = [
        format_custom_text,
        ' [', progressbar.DataSize(prefixes=('K', 'M', 'G')), '] ',
        progressbar.Bar(left='[', right=']'),
        ' [', progressbar.ETA(), '] ',
    ]
    with open(out_file, 'wb') as f:
        total_length = int(r.headers.get('content-length'))
        if total_length >= 1024:
            chunk_size = 1024
            num_bars = total_length / chunk_size
        else:
            chunk_size = 1
            num_bars = total_length / chunk_size
        bar = progressbar.ProgressBar(max_value=num_bars, widgets=widgets).start()
        i = 0
        for chunk in r.iter_content(chunk_size=chunk_size):
            format_custom_text.update_mapping(f=out_file)
            f.write(chunk)
            f.flush()
            os.fsync(f.fileno())
            bar.update(i)
            i += 1
        bar.finish()
