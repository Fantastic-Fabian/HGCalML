#!/usr/bin/env python3
"""
Analysis script to run of the predictions of the model.
"""

import os
import argparse
import pickle
import gzip
import mgzip
import pandas as pd

from OCHits2Showers import OCHits2ShowersLayer
from OCHits2Showers import process_endcap2, OCGatherEnergyCorrFac2
from ShowersMatcher2 import ShowersMatcher
from hplots.hgcal_analysis_plotter import HGCalAnalysisPlotter
import extra_plots as ep


def analyse(preddir, pdfpath, beta_threshold, distance_threshold, iou_threshold,
        matching_mode, analysisoutpath, nfiles, nevents,
        local_distance_scaling, is_soft, de_e_cut, angle_cut,
        energy_mode='hits'):
    """
    Analyse model predictions
    This includes:
    * building showers
    * matching them to truth showers
    * calculating efficiencies
    * calculating energy resolution
    * calculating pid prediction accuracy
    * plotting all of the above
    """

    hits2showers = OCHits2ShowersLayer(
        beta_threshold,
        distance_threshold,
        local_distance_scaling)
    showers_matcher = ShowersMatcher(matching_mode, iou_threshold, de_e_cut, angle_cut)

    energy_gatherer = OCGatherEnergyCorrFac2()

    files_to_be_tested = [
        os.path.join(preddir, x)
        for x in os.listdir(preddir)
        if (x.endswith('.bin.gz') and x.startswith('pred'))]
    if nfiles!=-1:
        files_to_be_tested = files_to_be_tested[0:min(nfiles, len(files_to_be_tested))]

    showers_dataframe = pd.DataFrame()
    features = []
    truth = []
    prediction = []
    processed = []
    alpha_ids = []
    noise_masks = []
    matched = []
    event_id = 0

    ###############################################################################################
    ### Loop over all events ######################################################################
    ###############################################################################################

    for i, file in enumerate(files_to_be_tested):
        print(f"Analysing file {i}/{len(files_to_be_tested)}")
        with mgzip.open(file, 'rb') as analysis_file:
            file_data = pickle.load(analysis_file)
        for j, endcap_data in enumerate(file_data):
            if (nevents != -1) and (j > nevents):
                continue
            print(f"Analysing endcap {j}/{len(file_data)}")
            features_dict, truth_dict, predictions_dict = endcap_data
            features.append(features_dict)
            prediction.append(predictions_dict)
            truth.append(truth_dict)

            noise_mask = predictions_dict['no_noise_sel']
            noise_masks.append(noise_mask)
            filtered_features = ep.filter_features_dict(features_dict, noise_mask)
            filtered_truth = ep.filter_truth_dict(truth_dict, noise_mask)

            processed_pred_dict, pred_shower_alpha_idx = process_endcap2(
                    hits2showers,
                    energy_gatherer,
                    filtered_features,
                    predictions_dict,
                    energy_mode=energy_mode)

            alpha_ids.append(pred_shower_alpha_idx)
            processed.append(processed_pred_dict)
            showers_matcher.set_inputs(
                features_dict=filtered_features,
                truth_dict=filtered_truth,
                predictions_dict=processed_pred_dict,
                pred_alpha_idx=pred_shower_alpha_idx
            )
            showers_matcher.process()
            dataframe = showers_matcher.get_result_as_dataframe()
            matched_truth_sid, matched_pred_sid = showers_matcher.get_matched_hit_sids()
            matched.append((matched_truth_sid, matched_pred_sid))

            dataframe['event_id'] = event_id
            event_id += 1
            showers_dataframe = pd.concat((showers_dataframe, dataframe))
            processed_dataframe = ep.dictlist_to_dataframe(processed)

    ###############################################################################################
    ### New plotting stuff ########################################################################
    ###############################################################################################

    ### Tracks versus hits ########################################################################
    fig = ep.tracks_vs_hits(showers_dataframe)
    fig.savefig(os.path.join('.', 'median_ratios.jpg'))

    ### Efficiency plots ##########################################################################
    fig_eff = ep.efficiency_plot(showers_dataframe)
    fig_eff.savefig(os.path.join('.', 'efficiency.jpg'))

    ### Resolution plots ##########################################################################
    fig_res = ep.energy_resolution(showers_dataframe)
    fig_res.savefig(os.path.join('.', 'energy_resolution.jpg'))

    ### Energy uncertainty plot ###################################################################
    fig_unc = ep.within_uncertainty(showers_dataframe)
    fig_unc.savefig(os.path.join('.', 'within_uncertainty.jpg'))

    # This is only to write to pdf files
    scalar_variables = {
        'beta_threshold': str(beta_threshold),
        'distance_threshold': str(distance_threshold),
        'iou_threshold': str(iou_threshold),
        'matching_mode': str(matching_mode),
        'is_soft': str(is_soft),
        'de_e_cut': str(de_e_cut),
        'angle_cut': str(angle_cut),
    }

    if len(analysisoutpath) > 0:
        analysis_data = {
            'showers_dataframe' : showers_dataframe,
            'events_dataframe' : None,
            'scalar_variables' : scalar_variables,
            'alpha_ids'        : alpha_ids,
            'noise_masks': noise_masks,
            'matched': matched,
        }
        if not args.slim:
            analysis_data['processed_dataframe'] = processed_dataframe
            analysis_data['features'] = features
            analysis_data['truth'] = truth
            analysis_data['prediction'] = prediction
        with gzip.open(analysisoutpath, 'wb') as output_file:
            print("Writing dataframes to pickled file",analysisoutpath)
            pickle.dump(analysis_data, output_file)

    if len(pdfpath)>0:
        plotter = HGCalAnalysisPlotter()
        plotter.set_data(showers_dataframe, None, '', pdfpath, scalar_variables=scalar_variables)
        plotter.process()

    print("DONE")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        'Analyse predictions from object condensation and plot relevant results')
    parser.add_argument('preddir',
        help='Directory with .bin.gz files or a txt file with full paths of the \
            bin-gz files from the prediction.')
    parser.add_argument('-p',
        help="Output directory for the final analysis pdf file (otherwise, it won't be produced)",
        default='')
    parser.add_argument('-b', help='Beta threshold (default 0.1)', default='0.1')
    parser.add_argument('-d', help='Distance threshold (default 0.5)', default='0.5')
    parser.add_argument('-i', help='IOU threshold (default 0.1)', default='0.1')
    parser.add_argument('-m', help='Matching mode', default='iou_max')
    parser.add_argument('--analysisoutpath',
        help='Will dump analysis data to a file to remake plots without re-running everything.',
        default='')
    parser.add_argument('--nfiles',
        help='Maximum number of files. -1 for everything in the preddir',
        default=-1)
    parser.add_argument('--no_local_distance_scaling', help='With local distance scaling',
        action='store_true')
    parser.add_argument('--de_e_cut', help='dE/E threshold to allow match.', default=-1)
    parser.add_argument('--angle_cut', help='Angle cut for angle based matching', default=-1)
    parser.add_argument('--no_soft', help='Use condensate op', action='store_true')
    parser.add_argument('--nevents', help='Maximum number of events (per file)', default=-1)
    parser.add_argument('--emode', help='Mode how energy is calculated', default='hits')
    parser.add_argument('--slim',
        help="Produce only a small analysis.bin.gz file. \
            Only applicable if --analysisoutpath is set",
        action='store_true')


    args = parser.parse_args()

    analyse(preddir=args.preddir,
            pdfpath=args.p,
            beta_threshold=float(args.b),
            distance_threshold=float(args.d),
            iou_threshold=float(args.i),
            matching_mode=args.m,
            analysisoutpath=args.analysisoutpath,
            nfiles=int(args.nfiles),
            local_distance_scaling=not args.no_local_distance_scaling,
            is_soft=not args.no_soft,
            de_e_cut=float(args.de_e_cut),
            angle_cut=float(args.angle_cut),
            nevents=int(args.nevents),
            energy_mode=str(args.emode),
            )
