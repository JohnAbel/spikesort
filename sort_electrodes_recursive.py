# -*- coding: utf-8 -*-
"""
Created on Fri May 27 16:48:41 2016

@author: abel, probably mazuski
"""

from __future__ import division

import numpy  as np
import scipy as sp
from sklearn import decomposition, cluster
import neuroshare as ns
import Electrode
from time import time
from concurrent import futures # requires pip install futures
import os
from collections import Counter

import matplotlib as mpl
import matplotlib.pyplot as plt


#trial data
experiment = 'data/032016_1104amstart/'
enames= np.sort(np.load(experiment+'numpy_database/enames.npy'))
files_in_folder = np.sort(os.listdir(experiment+'numpy_database'))[:-1]
mcd_labels = []
for filei in files_in_folder:
    if filei[0]=='.':
        pass
    else:
        mcd_labels.append(filei)



def child_categorize(inputs):
    """
    A function which sorts spikes for a single electrode by name. Uses child 
    processes to reduce memory load.
    """
    # use child process to keep it trill
    with futures.ProcessPoolExecutor(max_workers=1) as executor:
        result = executor.submit(categorize, inputs).result()
    return result

def categorize(inputs):
    """
    A function which sorts spikes for a single electrode by name.
    
    ----
        (ename, dbpath, mcd_idxs, pca_data_noise, gmm_data_noise, noise_std,
             pca_tree, gmm_tree, std_tree) = inputs
    ----
    """
    # set up inputs
    (ename, dbpath, mcd_idxs, pca_data_noise, gmm_data_noise, noise_std,
             pca_tree, gmm_tree, std_tree) = inputs
    try:
        #remove noise cluster
        ele1 = Electrode.Electrode(ename, database_path=dbpath, 
                                   mcd_idxs=mcd_idxs) 
                                   
        #categorize the spikes using em
        ele1.sort_spikes(pca_param=pca_data_noise, gmm_param=gmm_data_noise, 
                         method='em', precalc_std= noise_std)
        ele1.remove_noise_cluster(method='mean_profile')
        # sort the results
        if ele1.num_clusters > 1:
            noise_free_data = np.vstack(ele1.neurons.values())
            noise_free_times = np.hstack(ele1.neuron_spike_times.values())
            ele1.recursive_sort_spikes(noise_free_data,
                                       noise_free_times,
                                       pca_tree,
                                       gmm_tree,
                                       std_tree, final_method='std', 
                                       )
                                   
            result = [[] for i in range(ele1.num_clusters)] 
            for i in range(ele1.num_clusters):
                result[i] = np.asarray(ele1.neuron_spike_times[str(i)])
        else: 
            result=0    
    except: 
        result = -1
    return result

def sort_electrode(ename, dbpath, mcd_labels, batch_size, full_ele, 
                   savenpy=False, saveplots=False):
    """
    Function for sorting a single electrode completely. Currently only serial.
    
    ----
    ename : str
        Name of the spike being tested.
    paths : list(str)
        Paths to all the .mcd files being used.
    batch_size : int
        Number of files to process at once. I usually use 10, but this does
        create a large RAM load
    full_ele : Electrode.Electrode
        The electrode which has been resampled across all times. This function
        handles the spike sorting, and recursive sorting.
    savenpy : str (optional, defaults to false)
        Will save a numpy array of each neuron's firing times to this directory
    ----
    """
    # fit a gmm to remove the noise
    full_ele.fit_gmm(thresh='bics')
    cluster_count = full_ele.num_clusters
    if cluster_count == 1:
        # there is only noise
        return [], 0
    
    else:
        #deconstruct pca, gmm
        pca_data_noise = full_ele.pca_parameters
        gmm_data_noise = full_ele.gmm_parameters
        precalc_std = full_ele.calc_standard_deviation
        # sort electrode using EM to categorize ALL spikes
        full_ele.sort_spikes(method='em', precalc_std = precalc_std)
        # remove the noise cluster 
        full_ele.remove_noise_cluster()
        noise_free_data = np.vstack(full_ele.neurons.values())
        noise_free_times = np.hstack(full_ele.neuron_spike_times.values())
        
        # do a recursive sorting
        pca_tree, gmm_tree, std_tree = full_ele.recursive_fit_gmm(
                            noise_free_data, noise_free_times, pca_data_noise)
        full_ele.recursive_sort_spikes(noise_free_data, noise_free_times, 
                              pca_tree, gmm_tree, std_tree, final_method='std')
        neuron_count = full_ele.num_clusters

        # input data for sorting
        chunks = [mcd_labels[x:x+batch_size] for x 
                    in range(0, len(mcd_labels), batch_size)]
        inputs = [
            [ename, dbpath, chunk, pca_data_noise, gmm_data_noise, precalc_std,
             pca_tree, gmm_tree, std_tree]    for chunk in chunks]
        
        # feed the inputs to the categorization function
        outputs = []
        for inputi in inputs[:]:
            # consider parallelizing
            outputs.append(child_categorize(inputi))
        
        # get the outputs into a reasonable format
        firing_times = [[] for _ in range(neuron_count)]
        for idx,output in enumerate(outputs):
            if output==-1: pass # ignore if no output
            else:
                for neuron_index in range(neuron_count):
                    firing_times[neuron_index].append(
                            output[neuron_index])
        spike_time_arrays = []
        for i in range(neuron_count):
            if len(firing_times[i])>0:
                spike_time_arrays.append(np.hstack(firing_times[i]))
            else:
                spike_times_arrays.append(np.array([0]))
                                        
                                        
        # saving the numpy arrays, and the plots
        if savenpy is not False:
            #plots
            if saveplots is not False:
                fig2, waveforms = full_ele.plot_mean_profile(return_fig=True)
                fig2.savefig(saveplots+ename+'_spike_profiles.png')
                plt.clf()
                plt.close(fig2)
                fig3 = full_ele.plot_through_time(noise_free_times, return_fig=True)
                fig3.savefig(saveplots+ename+'_spikes_through_time.png')
                np.savetxt(saveplots+ename+
                                '_waveform.csv', waveforms, delimiter=',')
                plt.clf()
                plt.close(fig3)
                for pc in range(full_ele.num_comp)[1:]:
                    fig1 = full_ele.plot_clustering(return_fig=True,pc2=pc)
                    fig1.savefig(saveplots+ename+str(pc)+'pc_clusters.png')
                    plt.clf()
                    plt.close(fig1)
                    fig3 = full_ele.plot_heatmap(return_fig=True,  pc2=pc)
                    fig3.savefig(saveplots+ename+str(pc)+'pc_heatmap.png')
                    plt.clf()
                    plt.close(fig3)

            # numpy arrays
            for i in range(neuron_count):
                np.save(savenpy+ename+'_cluster'+str(i)+'_profile.npy',
                            full_ele.neurons[str(i)].mean(0))
                np.save(savenpy+ename+'_neuron'+str(i)+'_times.npy',
                            spike_time_arrays[i])
                            
        return spike_time_arrays, neuron_count
    



if __name__=='__main__':
    # Set up the directories for saving the results
    # if the folder exists, this prevents it from being overwritten
    # if you want to overwrite it, just delete it.
    
    if os.path.isdir(experiment+'numpy_neurons_recursive'):
        print ("Numpy neurons already exists in "+experiment+
                ". Please delete or select a new location.")
        import sys
        sys.exit()
    else: os.mkdir(experiment+'numpy_neurons_recursive')
    
    # save all files to csv, save plots
    result_path = experiment+'numpy_neurons_recursive/'
    if os.path.isdir(experiment+'/sorting_results'):
        print ("Sorting results already exists in "+experiment+
                ". Please delete or select a new location.")
        import sys
        sys.exit()
    else: 
        os.mkdir(experiment+'/sorting_results')    
        os.mkdir(experiment+'/sorting_results/csv')
        os.mkdir(experiment+'/sorting_results/plots') 
    
    
    # section for sorting all spikes.
    timer = Electrode.laptimer()
    neuron_count = []
    for ename in enames:    
        try:
            # LOAD RESAMPLED DATA
            rda = np.load(experiment+'subsampled_test_sets/'+ename+'_rda.npy')
            tda = np.load(experiment+'subsampled_test_sets/'+ename+'_tda.npy')
            full_ele = Electrode.Electrode(ename)# ignore all the names etc
            full_ele.load_array_data(rda, tda)
            
            # SORT THE SPIKES
            spks_sorted, nc = sort_electrode(
               ename, experiment, mcd_labels, 10, full_ele, 
               savenpy=experiment+'numpy_neurons_recursive/',
               saveplots=experiment+'sorting_results/plots/')
               
            print "Sorted for "+str(ename)
        except IOError:
            print "No spikes found for channel "+ename[-3:]

    print ("Time to serially sort all spikes "
                    +str(round(timer(),2))+"s.")
    
    # define plots
    def plot_frate(spike_times, window=600):
        times,frates = Electrode.firing_rates(spike_times, win=window)
        fig = plt.figure()
        plt.plot(times/3600, frates,'k.')
        plt.xlim([0,np.max(times/3600)])
        plt.xlabel('Time (h)')
        plt.tight_layout()
        plt.ylabel('10-min Mean Freq. (Hz)')
        return fig
    
    def plot_isi_hist(spike_times):
        isi = np.diff(spike_times)
        isi_millis = 1000*isi
        fig = plt.figure()
        ax = plt.subplot()
        ax.hist(isi_millis, bins=np.linspace(0,1000,101))
        ax.set_xlabel('ISI (ms)')
        #ax.set_xscale('log')
        ax.set_ylabel('Count')
        plt.tight_layout()
        return fig
        
    

    # process the python neurons
    result_path = experiment+'numpy_neurons_recursive'
    nfiles = np.sort(os.listdir(result_path))
    for nn in nfiles:
        if nn[-3:]=='npy' and nn[4]=='n':
            times = np.load(result_path+'/'+nn)
            if len(times) > 0:
                try:
                    np.savetxt(experiment+'/sorting_results/csv/'+nn[:-4]+
                                '.csv', times, delimiter=',')
                    #save plots
                    fig1 = plot_frate(times)
                    fig1.savefig(experiment+'/sorting_results/plots/'
                                        +nn[:11]+'_rate.png')
                    plt.clf()
                    plt.close(fig1)
                    fig2 = plot_isi_hist(times)
                    fig2.savefig(experiment+'/sorting_results/plots/'
                                        +nn[:11]+'_isihist.png')
                    plt.clf()
                    plt.close(fig2)
                except: print 'failed for'+nn
            
            
            
