import pandas as pd
import numpy as np
from typing import Callable
from __future__ import annotations


class Experiment:

    # auch noch dic mit ("ptm"->"ptm-token-in-seq") um sequences in Experiments zu standardisieren
    def __init__(self, name: str, seq: np.ndarray, charge: np.ndarray,
                 ccs: np.ndarray, intensity: np.ndarray, mz: np.ndarray,
                 raw_file: np.ndarray, evidence_id: np.ndarray):
        self.raw_dict = dict(zip(set(raw_file), range(len(set(raw_file)))))
        raw_file_int = np.vectorize(self.raw_dict.get, otypes=[int])(raw_file)
        self.name = name
        df = pd.DataFrame({"sequence": seq, "charge": charge, "ccs": ccs,
                           "intensity": intensity, "mz": mz, "raw_file": raw_file_int,
                           "id": evidence_id})
        self.data = self._cleanup(df)

    # alternative constructors
    @classmethod
    def empty_experiment(cls, name):
        args = [[]]*7
        return cls(name, *args)

    @classmethod
    def _from_whole_DataFrame(cls, name, df):
        # instanciate empty experiment and fill mit df
        new_exp = cls.empty_experiment(name)
        new_exp.data = df
        return new_exp

    @classmethod
    def from_MaxQuant_DataFrame(cls, df: pd.DataFrame, name: str):
        cls._validate(df)
        return cls(name, df["Modified sequence"].values, df["Charge"].values, df["CCS"].values, df["Intensity"].values, df["m/z"].values, df["Raw file"].values, df["id"].values)

    def __repr__(self):
        return "Experiment: {}\n".format(self.name) + self.data.__repr__()

    @staticmethod
    def _validate(obj):
        # verify presence of necessary columns
        cols = ["Modified sequence", "Charge", "m/z",
                "CCS", "Intensity", "Raw file", "Mass"]
        if not set(cols).issubset(set(obj.columns)):
            raise AttributeError("Must have {}.".format(cols))

    @staticmethod
    def _reduce_dup_feats(df: pd.DataFrame) -> pd.DataFrame:
        """
        aggregates ("modified_sequence", "charge", "ccs")-duplicates
        """
        # calculate total intensity of (seq, z, ccs) duplicates in table (across runs)
        subset = ["sequence", "charge", "ccs"]
        # groupby() removes rows with nan values in subset additionally to grouping
        df = df.groupby(by=subset)

        #  agg() agregates and changes column names
        #! maybe instead of list and set use tuples
        df = df.agg(intensities=("intensity", list),
                    feat_intensity=("intensity", "sum"),
                    mz=("mz", set), occurences=("sequence", "count"),
                    raw_files=("raw_file", set), ids=("id", list)
                    ).reset_index(drop=False)
        print("_reduce_dup_feats():", df.columns)
        return df

    @staticmethod
    def _drop_unnecessary_rows(df: pd.DataFrame) -> pd.DataFrame:
        df = df.dropna()
        df = df.drop(df[df.charge == 1].index)
        print("_drop_unnecessary_rows():", df.columns)

        return df

    @staticmethod
    def _sort_feats(df: pd.DataFrame) -> pd.DataFrame:
        df = df.sort_values(
            by=["sequence", "charge", "ccs"]).reset_index(drop=True)
        print("_sort_feats():", df.columns)
        return df

    @classmethod
    def _cleanup(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        removing rows with nan in any column of and singly charged features.
        """
        if not df.shape[0]:
            return df
        df = cls._drop_unnecessary_rows(df)
        df = cls._reduce_dup_feats(df)
        return cls._sort_feats(df)

    # @staticmethod
    # def _container_in_cols(df: pd.DataFrame, target_cols):
    #     """
    #     identifies which columns contains container (list, numpy.array, set, dict, tuple) as values
    #     @return: numpy array with bools which column contains container
    #     """
    #     target_cols_idx = [i for i, col_name in enumerate(df.columns) if col_name in target_cols]
    #     mask = np.zeros((len(df.columns)), dtype = bool)
    #     for i, val in enumerate(df.iloc[0, target_cols_idx]):
    #             try:
    #                 # check if val is a container introduced by aggregation
    #                 if len(val):
    #                     mask[target_cols_idx[i]] = True
    #             except TypeError as err:
    #                 pass
    #     return mask
    @staticmethod
    def add_main_feat_values(df, condition_main):
        """
        adds columns with values of respective main_feature to each row. For each column in target_cols that contains a container data type, a
        seperate colum with name max_feat_{colname} is generated with the max value of respective container 
        :param condition_main: column which determines main feature. currently only "feat_intensity" or "occurences" considered
        :return: dataframe with len(target_columns) additinal columns with "main_" prefix to targeted column name
        """
        target_col = ["ccs"]

        subset = ["sequence", "charge"]
        main_vals_col = np.empty((df.shape[0],))
        main_vals_col.fill(np.nan)
        new_col_name = "main_ccs"
        main_feat_df = pd.DataFrame(
            {new_col_name: main_vals_col}, index=df.index)

        for _, g_df in df.groupby(by=subset):
            idx_main = g_df[condition_main].idxmax()
            main_vals = g_df.loc[idx_main, target_col].values
            main_feat_df.loc[g_df.index] = np.full(
                (g_df.shape[0], main_vals.shape[0]), main_vals)

        return pd.concat([df, main_feat_df], axis=1)

    @staticmethod
    def calc_diffs_to_main_feat(df, cols, secondary_level=False):
        """
        calculates difference between value in cols and corresponding main_feature value of respective main_feature
        @df: pandas DataFrame object
        @cols: itrable with column names to for which value differences to main_feature are determined
        @secondary_level: for usage on subset. ulitmately adds suffix to additional columns with calculated values
        @return: dataframe with len(cols) additinal columns with "difference_" prefix to column names in cols
        """
        secondary_col = ""
        if secondary_level:
            secondary_col = "_secondary"
        for col in cols:
            if col not in df.columns:
                raise KeyError(
                    "Column {} not present in given DataFrame".format(col))

        for col in cols:
            main_col = "main_" + col+secondary_col
            df.loc[:, "difference_" + col +
                   secondary_col] = df[col] - df[main_col]

        return df

    def prep_feat_analysis(self, condition_main):
        """wraps pipeline for preperation for modality class assignment
        @df: pandas DataFrame
        @condition_main: column on which the main feat identification is based
        @return: datframe with additional max_feat_{colname} or
        """
        df = self.add_main_feat_values(self.data, condition_main)
        print("after add_main_feat_values(): ", df.columns)
        df = self.calc_diffs_to_main_feat(df, ["ccs"])
        print("after calc_diffs_to_main_feat(): ", df.columns)
        return self._from_whole_DataFrame(self.name, df)

    @staticmethod
    def get_outliers_loc(df, sd, scale_factor=1, secondary_level=False):
        """"
        gets row names of secondary features
        @return: list of row names (pandas indices) of scndry feats in df
        """
        secondary_col = ""
        if secondary_level:
            secondary_col = "_secondary"

        df = df.loc[:, ["ccs", "main_ccs"+secondary_col]]
        scndry_feat_idx = []
        for i in df.index:
            ccs, main_ccs = df.loc[i].values
            if (main_ccs - (main_ccs*sd*scale_factor) > ccs) or (main_ccs + (main_ccs*sd*scale_factor) < ccs):
                scndry_feat_idx.append(i)
        scndry_feat_idx = np.array(scndry_feat_idx)
        return scndry_feat_idx

    def add_modality_col(self, secondary_level=False):
        """
        @metric: string. column of df. metric that is used to quantify features
        """
        secondary_col = ""
        if secondary_level:
            secondary_col = "_secondary"

        indices = dict()
        df = self.data.loc[:]
        df.loc[:, "modality"+secondary_col] = np.nan
        dups = df.duplicated(subset=["sequence", "charge"], keep=False).values
        indices["unimodal"] = df.loc[np.invert(dups)].index.values
        df2 = df.loc[dups]
        indices["main"] = df2.loc[df2["difference_ccs" +
                                      secondary_col] == 0].index.values
        sd = (df2.difference_ccs/df2.main_ccs).std()

        indices["secondary"] = df2.loc[self.get_outliers_loc(
            df2, sd, 1, secondary_level=secondary_level)].index.values

        indices["measurement_error"] = df2.loc[~df2.index.isin(
            np.concatenate(list(indices.values())))].index.values

        for k, v in indices.items():
            df.loc[v, "modality"+secondary_col] = k

        return self._from_whole_DataFrame(self.name, df)

    @staticmethod
    def _find_false_bimodals(df: pd.DataFrame) -> pd.DataFrame:
        """
        @df: dataframe with modality column and vlaues (unimodal, main, measurement_error, secondary)
        @return: pandas dataframe containing only rows falsely identified as bimodal
        """
        sndry = df.loc[df.modality == "secondary"]
        main_and_meas_err = df.loc[(df.modality == "main") | (
            df.modality == "measurement_error")].copy()

        # carry the "old" row-labels over for after merge
        main_and_meas_err.loc[:, 'index'] = main_and_meas_err.index
        # select only (seq, cahrge) instances not present in "secondary"
        df_new_unimodals_pre_agg = main_and_meas_err.merge(sndry.loc[:, ["sequence", "charge", "ccs"]],
                                                           how="left", on=["sequence", "charge"],
                                                           suffixes=[None, "_right"]).drop_duplicates(subset=["index"]).set_index("index")
        df_new_unimodals_pre_agg = df_new_unimodals_pre_agg.loc[df_new_unimodals_pre_agg.ccs_right.isna(
        )]

        df_new_unimodals_pre_agg = df_new_unimodals_pre_agg.drop(
            columns=["modality", "ccs_right"])

        return df_new_unimodals_pre_agg

    @staticmethod
    def agg_with_container_in_cols(df: pd.DataFrame, ccs_agg_func: Callable[[pd.Series], float], modality_class: str) -> pd.DataFrame:
        """
        aggregates (modified_sequence, charge)-duplicates for dfs with containers in columns. CCS values are
        aggregated according to ccs_agg_func
        @df: df that only contains instances that were labeles as 'main' and 'measurement_error' but do not have
        a corresponding 'secondary' instance and therefore are not actually bimodal
        @cc_agg_func: function to use for aggregation of CCS values of (modified_sequence, charge)-duplicates
        @modality_class: new modality class assigned to all feats in newly aggregated df
        """
        def concat_sets(x): return set().union(*x)

        aggregated_df = df.groupby(by=["sequence", "charge"]).agg(
            intensities=("intensities", "sum"), feat_intensity=("feat_intensity", "sum"),
            occurences=("occurences", "sum"), raw_files=("raw_files", concat_sets),
            ids=("ids", "sum"), ccs=("ccs", ccs_agg_func)
        ).reset_index(drop=False)
        aggregated_df["modality"] = modality_class
        return aggregated_df

    @staticmethod
    def _replace_rows_in_df(df: pd.DataFrame, df_rows_to_remove: pd.DataFrame, df_rows_to_add:  pd.DataFrame) -> pd.DataFrame:
        df = df.loc[~df.index.isin(df_rows_to_remove.index)]

        return pd.concat([df, df_rows_to_add], ignore_index=True, sort=False)

    def false_bimodal_to_unimodal(self, weight_col_for_ccs_agg: str) -> Experiment:
        """reduces false bimodal feats that contained only "main" and "measurement_error" as modality class into "unimodal"
        :weigth_col_for_ccs_agg: column name used for weight during aggregation. Use "occurences" or "feat_intensity".
        :return: Experiment without bimodal feats that do not have any secondary feat
        """

        # thought on making weight_col_for_ccs_agg into 0 or 1 as alias for "occurences" or "feat_intensity" in parameter. to
        # dic = {0: "occurences", 1: "feat_intensity"}
        # weight_col_for_ccs_agg = dic[weight_col_for_ccs_agg]

        df_false_bimodals_pre_agg = self._find_false_bimodals(self.data)

        # "weight_col_for_ccs_agg"-weighted mean.
        def wm(x): return np.average(
            x, weights=df_false_bimodals_pre_agg.loc[x.index, weight_col_for_ccs_agg].values)

        df_false_bimodals_post_agg = self.agg_with_container_in_cols(
            df_false_bimodals_pre_agg, ccs_agg_func=wm, modality_class="unimodal")
        df = self._replace_rows_in_df(
            self.data, df_false_bimodals_pre_agg, df_false_bimodals_post_agg)
        df.loc[df.modality == "unimodal", [
            "main_ccs", "difference_ccs"]] = np.nan
        return self._from_whole_DataFrame(self.name, df)

    @staticmethod
    def _find_true_bimodals(df: pd.DataFrame) -> pd.DataFrame:
        """
        @df: dataframe with modality column containing vlaues (unimodal, main, measurement_error, secondary)
        @return: dataframe 
        """
        sndry = df.loc[df.modality == "secondary"]
        main_and_meas_err = df.loc[(df.modality == "main") | (
            df.modality == "measurement_error")].copy()

        # carry the "old" row-labels over for after merge
        main_and_meas_err.loc[:, 'index'] = main_and_meas_err.index
        # select only (seq, charge) instances present in "secondary"
        df_new_unimodals_pre_agg = main_and_meas_err.merge(sndry.loc[:, ["sequence", "charge", "ccs"]],
                                                           how="left", on=["sequence", "charge"],
                                                           suffixes=[
                                                               None, "_right"]
                                                           ).drop_duplicates(subset=["index"]).set_index("index")    # drop duplicates in subset "index" to have only one representative of each feature like in main_and_meas_err

        df_new_unimodals_pre_agg = df_new_unimodals_pre_agg.loc[df_new_unimodals_pre_agg.ccs_right.notna(
        )]

        df_new_unimodals_pre_agg = df_new_unimodals_pre_agg.drop(
            columns=["modality", "ccs_right"])

        return df_new_unimodals_pre_agg

    def agg_bimodal_main_and_measurement_errors(self, weight_col_for_ccs_agg):
        """aggregates all those features labeled as "main" and "measuremen_error" out of truly bimodal feats"""
        df_true_bimodals_pre_agg = self._find_true_bimodals(self.data)
        def wm(x): return np.average(
            x, weights=df_true_bimodals_pre_agg.loc[x.index, weight_col_for_ccs_agg])

        df_true_bimodals_post_agg = self.agg_with_container_in_cols(
            df_true_bimodals_pre_agg, ccs_agg_func=wm, modality_class="main")
        result_df = self._replace_rows_in_df(
            self.data, df_true_bimodals_pre_agg, df_true_bimodals_post_agg)
        return self._from_whole_DataFrame(self.name, result_df)


#     def assign_modalities(self, df, target_cols):
#         """
#         wraps pipeline for modality class asignment of features
#         @df: pandas DataFrame
#         @target_cols: values of interest for modality assignment, like ccs or score
#         @return: pandas Dataframe with
#         """
#         new_exp = self.prep_feat_analysis(
#             df, target_cols, condition_main="occurences", aggregate=True, remove_unimod=False)
#         new_exp = new_exp.add_modality_col()
#         df = false_bimodal_to_unimodal(df, "occurences")
#         df = agg_bimodal_main_and_measurement_errors(df, "occurences")
#         df = agg_secondary_feats(df, "occurences")
#         df = set_to_list(df)
#         return _from_whole_DataFrame(self.name, df)


    def intrinsic_align(self):
        pass

    def master_align(self, other):
        pass


# def read_evidence(path):
#     relevant_cols = ["Modified sequence", "Charge", "m/z", "CCS", "Intensity", "Raw file", "Mass"]
#     df = read_raw_and_filter(relevant_cols, path)
#     validate(df)
#     return from_DataFrame(df)
