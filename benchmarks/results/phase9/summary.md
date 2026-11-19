# Executed Phase 9 summaries

All individual runs, warnings and unsuccessful cases are retained in suite JSON artifacts. Repeated seeds and duplicated clean controls are not independent domains.

## Public-data injected-label benchmark

AP is undefined for clean controls. Means below are descriptive across three seeds on each dataset/condition. No pooled cross-domain superiority test.

| Dataset | Noise | Rate | Method | AP mean | FPR mean | Precision mean | Recall mean |
|---|---|---|---|---|---|---|---|
| iris | class_labels | 0.0 | datagenome | undefined | 0.0185 | 0.0000 | undefined |
| iris | class_labels | 0.0 | low_observed_probability | undefined | 0.0407 | 0.0000 | undefined |
| iris | class_labels | 0.0 | neighborhood | undefined | 0.0630 | 0.0000 | undefined |
| iris | class_labels | 0.0 | oof_disagreement | undefined | 0.0407 | 0.0000 | undefined |
| iris | class_labels | 0.0 | random | undefined | 0.1111 | 0.0000 | undefined |
| iris | class_labels | 0.1 | datagenome | 0.5880 | 0.0412 | 0.6343 | 0.6296 |
| iris | class_labels | 0.1 | low_observed_probability | 0.8171 | 0.1481 | 0.4122 | 0.9259 |
| iris | class_labels | 0.1 | neighborhood | 0.8729 | 0.0988 | 0.5208 | 0.9630 |
| iris | class_labels | 0.1 | oof_disagreement | 0.4070 | 0.1235 | 0.4454 | 0.8889 |
| iris | class_labels | 0.1 | random | 0.1292 | 0.1152 | 0.0754 | 0.0741 |
| iris | class_labels | 0.2 | datagenome | 0.2960 | 0.0880 | 0.3951 | 0.2037 |
| iris | class_labels | 0.2 | low_observed_probability | 0.6375 | 0.3333 | 0.3588 | 0.7593 |
| iris | class_labels | 0.2 | neighborhood | 0.5843 | 0.2269 | 0.4830 | 0.8519 |
| iris | class_labels | 0.2 | oof_disagreement | 0.3247 | 0.2963 | 0.3661 | 0.7037 |
| iris | class_labels | 0.2 | random | 0.2140 | 0.1250 | 0.1057 | 0.0556 |
| iris | feature_labels | 0.0 | datagenome | undefined | 0.0185 | 0.0000 | undefined |
| iris | feature_labels | 0.0 | low_observed_probability | undefined | 0.0407 | 0.0000 | undefined |
| iris | feature_labels | 0.0 | neighborhood | undefined | 0.0630 | 0.0000 | undefined |
| iris | feature_labels | 0.0 | oof_disagreement | undefined | 0.0407 | 0.0000 | undefined |
| iris | feature_labels | 0.0 | random | undefined | 0.1111 | 0.0000 | undefined |
| iris | feature_labels | 0.1 | datagenome | 0.4601 | 0.0370 | 0.5655 | 0.4444 |
| iris | feature_labels | 0.1 | low_observed_probability | 0.7184 | 0.1317 | 0.3712 | 0.7037 |
| iris | feature_labels | 0.1 | neighborhood | 0.6905 | 0.0782 | 0.5587 | 0.8889 |
| iris | feature_labels | 0.1 | oof_disagreement | 0.3674 | 0.0864 | 0.4739 | 0.7037 |
| iris | feature_labels | 0.1 | random | 0.1129 | 0.1070 | 0.1310 | 0.1481 |
| iris | feature_labels | 0.2 | datagenome | 0.3417 | 0.0370 | 0.5952 | 0.2222 |
| iris | feature_labels | 0.2 | low_observed_probability | 0.8041 | 0.2731 | 0.4442 | 0.8704 |
| iris | feature_labels | 0.2 | neighborhood | 0.6741 | 0.1204 | 0.6162 | 0.7778 |
| iris | feature_labels | 0.2 | oof_disagreement | 0.4702 | 0.1898 | 0.5239 | 0.8333 |
| iris | feature_labels | 0.2 | random | 0.2367 | 0.1019 | 0.2817 | 0.1481 |
| iris | uniform_labels | 0.0 | datagenome | undefined | 0.0185 | 0.0000 | undefined |
| iris | uniform_labels | 0.0 | low_observed_probability | undefined | 0.0407 | 0.0000 | undefined |
| iris | uniform_labels | 0.0 | neighborhood | undefined | 0.0630 | 0.0000 | undefined |
| iris | uniform_labels | 0.0 | oof_disagreement | undefined | 0.0407 | 0.0000 | undefined |
| iris | uniform_labels | 0.0 | random | undefined | 0.1111 | 0.0000 | undefined |
| iris | uniform_labels | 0.1 | datagenome | 0.7340 | 0.0329 | 0.7305 | 0.8148 |
| iris | uniform_labels | 0.1 | low_observed_probability | 0.8776 | 0.1440 | 0.4335 | 0.9630 |
| iris | uniform_labels | 0.1 | neighborhood | 0.9292 | 0.0782 | 0.5796 | 0.9630 |
| iris | uniform_labels | 0.1 | oof_disagreement | 0.4659 | 0.1193 | 0.4833 | 0.9630 |
| iris | uniform_labels | 0.1 | random | 0.1803 | 0.1029 | 0.1663 | 0.1852 |
| iris | uniform_labels | 0.2 | datagenome | 0.6012 | 0.0417 | 0.7675 | 0.5370 |
| iris | uniform_labels | 0.2 | low_observed_probability | 0.8720 | 0.2176 | 0.5202 | 0.9444 |
| iris | uniform_labels | 0.2 | neighborhood | 0.8883 | 0.1481 | 0.6335 | 1.0000 |
| iris | uniform_labels | 0.2 | oof_disagreement | 0.5906 | 0.1435 | 0.6197 | 0.9259 |
| iris | uniform_labels | 0.2 | random | 0.2405 | 0.1111 | 0.2139 | 0.1111 |
| wdbc | class_labels | 0.0 | datagenome | undefined | 0.0166 | 0.0000 | undefined |
| wdbc | class_labels | 0.0 | low_observed_probability | undefined | 0.0313 | 0.0000 | undefined |
| wdbc | class_labels | 0.0 | neighborhood | undefined | 0.0450 | 0.0000 | undefined |
| wdbc | class_labels | 0.0 | oof_disagreement | undefined | 0.0313 | 0.0000 | undefined |
| wdbc | class_labels | 0.0 | random | undefined | 0.1036 | 0.0000 | undefined |
| wdbc | class_labels | 0.1 | datagenome | 0.3674 | 0.0575 | 0.5167 | 0.5392 |
| wdbc | class_labels | 0.1 | low_observed_probability | 0.5125 | 0.1010 | 0.4383 | 0.6961 |
| wdbc | class_labels | 0.1 | neighborhood | 0.5174 | 0.0858 | 0.5163 | 0.8137 |
| wdbc | class_labels | 0.1 | oof_disagreement | 0.3356 | 0.1010 | 0.4383 | 0.6961 |
| wdbc | class_labels | 0.1 | random | 0.1007 | 0.1042 | 0.0942 | 0.0980 |
| wdbc | class_labels | 0.2 | datagenome | 0.2127 | 0.1123 | 0.2808 | 0.1765 |
| wdbc | class_labels | 0.2 | low_observed_probability | 0.3757 | 0.1575 | 0.3398 | 0.3235 |
| wdbc | class_labels | 0.2 | neighborhood | 0.3814 | 0.1490 | 0.3534 | 0.3235 |
| wdbc | class_labels | 0.2 | oof_disagreement | 0.2451 | 0.1575 | 0.3398 | 0.3235 |
| wdbc | class_labels | 0.2 | random | 0.1930 | 0.1074 | 0.1705 | 0.0882 |
| wdbc | feature_labels | 0.0 | datagenome | undefined | 0.0166 | 0.0000 | undefined |
| wdbc | feature_labels | 0.0 | low_observed_probability | undefined | 0.0313 | 0.0000 | undefined |
| wdbc | feature_labels | 0.0 | neighborhood | undefined | 0.0450 | 0.0000 | undefined |
| wdbc | feature_labels | 0.0 | oof_disagreement | undefined | 0.0313 | 0.0000 | undefined |
| wdbc | feature_labels | 0.0 | random | undefined | 0.1036 | 0.0000 | undefined |
| wdbc | feature_labels | 0.1 | datagenome | 0.1836 | 0.0717 | 0.3466 | 0.3333 |
| wdbc | feature_labels | 0.1 | low_observed_probability | 0.2983 | 0.1194 | 0.3215 | 0.5098 |
| wdbc | feature_labels | 0.1 | neighborhood | 0.2232 | 0.0695 | 0.3061 | 0.2843 |
| wdbc | feature_labels | 0.1 | oof_disagreement | 0.2144 | 0.1194 | 0.3215 | 0.5098 |
| wdbc | feature_labels | 0.1 | random | 0.1094 | 0.1031 | 0.1037 | 0.1078 |
| wdbc | feature_labels | 0.2 | datagenome | 0.2023 | 0.0794 | 0.2086 | 0.0833 |
| wdbc | feature_labels | 0.2 | low_observed_probability | 0.2394 | 0.1038 | 0.2407 | 0.1324 |
| wdbc | feature_labels | 0.2 | neighborhood | 0.2241 | 0.0781 | 0.1421 | 0.0539 |
| wdbc | feature_labels | 0.2 | oof_disagreement | 0.2051 | 0.1038 | 0.2407 | 0.1324 |
| wdbc | feature_labels | 0.2 | random | 0.1942 | 0.1074 | 0.1705 | 0.0882 |
| wdbc | uniform_labels | 0.0 | datagenome | undefined | 0.0166 | 0.0000 | undefined |
| wdbc | uniform_labels | 0.0 | low_observed_probability | undefined | 0.0313 | 0.0000 | undefined |
| wdbc | uniform_labels | 0.0 | neighborhood | undefined | 0.0450 | 0.0000 | undefined |
| wdbc | uniform_labels | 0.0 | oof_disagreement | undefined | 0.0313 | 0.0000 | undefined |
| wdbc | uniform_labels | 0.0 | random | undefined | 0.1036 | 0.0000 | undefined |
| wdbc | uniform_labels | 0.1 | datagenome | 0.7919 | 0.0217 | 0.8135 | 0.8235 |
| wdbc | uniform_labels | 0.1 | low_observed_probability | 0.8888 | 0.0630 | 0.6255 | 0.9412 |
| wdbc | uniform_labels | 0.1 | neighborhood | 0.8109 | 0.0619 | 0.6296 | 0.9412 |
| wdbc | uniform_labels | 0.1 | oof_disagreement | 0.5940 | 0.0630 | 0.6255 | 0.9412 |
| wdbc | uniform_labels | 0.1 | random | 0.1436 | 0.0988 | 0.1382 | 0.1471 |
| wdbc | uniform_labels | 0.2 | datagenome | 0.7611 | 0.0281 | 0.8736 | 0.7696 |
| wdbc | uniform_labels | 0.2 | low_observed_probability | 0.8772 | 0.0879 | 0.7246 | 0.9167 |
| wdbc | uniform_labels | 0.2 | neighborhood | 0.7679 | 0.1062 | 0.6712 | 0.8480 |
| wdbc | uniform_labels | 0.2 | oof_disagreement | 0.6805 | 0.0879 | 0.7246 | 0.9167 |
| wdbc | uniform_labels | 0.2 | random | 0.2181 | 0.1013 | 0.2181 | 0.1127 |
| wine | class_labels | 0.0 | datagenome | undefined | 0.0093 | 0.0000 | undefined |
| wine | class_labels | 0.0 | low_observed_probability | undefined | 0.0187 | 0.0000 | undefined |
| wine | class_labels | 0.0 | neighborhood | undefined | 0.0312 | 0.0000 | undefined |
| wine | class_labels | 0.0 | oof_disagreement | undefined | 0.0187 | 0.0000 | undefined |
| wine | class_labels | 0.0 | random | undefined | 0.1059 | 0.0000 | undefined |
| wine | class_labels | 0.1 | datagenome | 0.5930 | 0.0515 | 0.6033 | 0.7333 |
| wine | class_labels | 0.1 | low_observed_probability | 0.8276 | 0.1306 | 0.4362 | 0.9667 |
| wine | class_labels | 0.1 | neighborhood | 0.8660 | 0.0653 | 0.6268 | 1.0000 |
| wine | class_labels | 0.1 | oof_disagreement | 0.4426 | 0.1134 | 0.4688 | 0.9333 |
| wine | class_labels | 0.1 | random | 0.0926 | 0.1168 | 0.0000 | 0.0000 |
| wine | class_labels | 0.2 | datagenome | 0.4272 | 0.0659 | 0.6006 | 0.3968 |
| wine | class_labels | 0.2 | low_observed_probability | 0.6862 | 0.1628 | 0.5636 | 0.8571 |
| wine | class_labels | 0.2 | neighborhood | 0.6719 | 0.1667 | 0.5794 | 0.9206 |
| wine | class_labels | 0.2 | oof_disagreement | 0.4442 | 0.1395 | 0.5520 | 0.6984 |
| wine | class_labels | 0.2 | random | 0.2165 | 0.1124 | 0.1553 | 0.0794 |
| wine | feature_labels | 0.0 | datagenome | undefined | 0.0093 | 0.0000 | undefined |
| wine | feature_labels | 0.0 | low_observed_probability | undefined | 0.0187 | 0.0000 | undefined |
| wine | feature_labels | 0.0 | neighborhood | undefined | 0.0312 | 0.0000 | undefined |
| wine | feature_labels | 0.0 | oof_disagreement | undefined | 0.0187 | 0.0000 | undefined |
| wine | feature_labels | 0.0 | random | undefined | 0.1059 | 0.0000 | undefined |
| wine | feature_labels | 0.1 | datagenome | 0.5601 | 0.0515 | 0.5556 | 0.6000 |
| wine | feature_labels | 0.1 | low_observed_probability | 0.8466 | 0.1237 | 0.4625 | 0.9667 |
| wine | feature_labels | 0.1 | neighborhood | 0.8640 | 0.0515 | 0.6687 | 1.0000 |
| wine | feature_labels | 0.1 | oof_disagreement | 0.5016 | 0.0997 | 0.5185 | 0.9667 |
| wine | feature_labels | 0.1 | random | 0.1146 | 0.1065 | 0.0905 | 0.1000 |
| wine | feature_labels | 0.2 | datagenome | 0.4895 | 0.1008 | 0.5448 | 0.4603 |
| wine | feature_labels | 0.2 | low_observed_probability | 0.7054 | 0.2442 | 0.4470 | 0.7937 |
| wine | feature_labels | 0.2 | neighborhood | 0.7092 | 0.1085 | 0.6688 | 0.8889 |
| wine | feature_labels | 0.2 | oof_disagreement | 0.4007 | 0.2209 | 0.4645 | 0.7619 |
| wine | feature_labels | 0.2 | random | 0.1951 | 0.1202 | 0.0905 | 0.0476 |
| wine | uniform_labels | 0.0 | datagenome | undefined | 0.0093 | 0.0000 | undefined |
| wine | uniform_labels | 0.0 | low_observed_probability | undefined | 0.0187 | 0.0000 | undefined |
| wine | uniform_labels | 0.0 | neighborhood | undefined | 0.0312 | 0.0000 | undefined |
| wine | uniform_labels | 0.0 | oof_disagreement | undefined | 0.0187 | 0.0000 | undefined |
| wine | uniform_labels | 0.0 | random | undefined | 0.1059 | 0.0000 | undefined |
| wine | uniform_labels | 0.1 | datagenome | 0.8644 | 0.0515 | 0.6686 | 0.9333 |
| wine | uniform_labels | 0.1 | low_observed_probability | 0.8946 | 0.1237 | 0.4486 | 0.9667 |
| wine | uniform_labels | 0.1 | neighborhood | 0.8990 | 0.0515 | 0.6687 | 1.0000 |
| wine | uniform_labels | 0.1 | oof_disagreement | 0.4626 | 0.1134 | 0.4725 | 0.9667 |
| wine | uniform_labels | 0.1 | random | 0.1256 | 0.1031 | 0.1275 | 0.1333 |
| wine | uniform_labels | 0.2 | datagenome | 0.7619 | 0.0620 | 0.7434 | 0.7302 |
| wine | uniform_labels | 0.2 | low_observed_probability | 0.9096 | 0.2016 | 0.5280 | 0.9206 |
| wine | uniform_labels | 0.2 | neighborhood | 0.8954 | 0.1202 | 0.6638 | 0.9683 |
| wine | uniform_labels | 0.2 | oof_disagreement | 0.5518 | 0.1550 | 0.5872 | 0.9048 |
| wine | uniform_labels | 0.2 | random | 0.2170 | 0.1008 | 0.2301 | 0.1270 |

## Drift sensitivity and false alerts

Three prespecified seeds per condition; effect screens and formal IID inference are distinct. Small counts do not establish population sensitivity or false-positive calibration.

| Scenario | Rows/window | Trials | Any effect alert | Any Holm rejection including MMD |
|---|---|---|---|---|
| category | 40 | 3 | 2 | 0 |
| category | 200 | 3 | 0 | 3 |
| clean | 40 | 3 | 2 | 0 |
| clean | 200 | 3 | 0 | 0 |
| conditional | 40 | 3 | 2 | 0 |
| conditional | 200 | 3 | 0 | 0 |
| dependence | 40 | 3 | 2 | 3 |
| dependence | 200 | 3 | 0 | 3 |
| label_frequency | 40 | 3 | 3 | 3 |
| label_frequency | 200 | 3 | 3 | 3 |
| large_mean | 40 | 3 | 3 | 3 |
| large_mean | 200 | 3 | 3 | 3 |
| missing | 40 | 3 | 3 | 0 |
| missing | 200 | 3 | 3 | 0 |
| new_category | 40 | 3 | 3 | 3 |
| new_category | 200 | 3 | 3 | 3 |
| small_mean | 40 | 3 | 2 | 1 |
| small_mean | 200 | 3 | 0 | 0 |
| variance | 40 | 3 | 3 | 2 |
| variance | 200 | 3 | 3 | 3 |

## Prespecified record-disjoint Digits interventions

Oracle arms use known injected truth, not model-predicted replacement labels. Writer dependence is unknown; bootstrap intervals are conditional on IID rows. All removals target the same prespecified count; insufficient candidate arms are unavailable.

| Seed | Arm | Status | Independent accuracy | Paired accuracy delta | 95% paired bootstrap |
|---|---|---|---|---|---|
| 11 | combined | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 11 | duplicates | insufficient_candidates | None | None | None |
| 11 | highest | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 11 | label_exclusion | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 11 | lowest | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 11 | oracle_correction | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 11 | original | scored | 1.0 | None | None |
| 11 | random | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 23 | combined | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 23 | duplicates | insufficient_candidates | None | None | None |
| 23 | highest | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 23 | label_exclusion | scored | 0.9833333333333333 | -0.01666666666666672 | [-0.06666666666666665, 0.0] |
| 23 | lowest | scored | 0.9833333333333333 | -0.01666666666666672 | [-0.06666666666666665, 0.0] |
| 23 | oracle_correction | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 23 | original | scored | 1.0 | None | None |
| 23 | random | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 37 | combined | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 37 | duplicates | insufficient_candidates | None | None | None |
| 37 | highest | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 37 | label_exclusion | scored | 0.9830508474576272 | -0.016949152542372836 | [-0.06779661016949157, 0.0] |
| 37 | lowest | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 37 | oracle_correction | scored | 1.0 | 0.0 | [0.0, 0.0] |
| 37 | original | scored | 1.0 | None | None |
| 37 | random | scored | 0.9830508474576272 | -0.016949152542372836 | [-0.06779661016949157, 0.0] |

## Runtime distribution

| Suite | Trials | Non-evaluated | Mean s | Median s | SD s | Max Python MiB |
|---|---|---|---|---|---|---|
| smoke | 3 | 0 | 0.4567 | 0.3066 | 0.5286 | 5.73 |
| leakage | 24 | 0 | 0.4955 | 0.5716 | 0.2186 | 5.71 |
| labels | 81 | 0 | 0.8294 | 0.6053 | 0.3497 | 54.64 |
| valuation | 15 | 0 | 15.5025 | 17.2307 | 8.5649 | 5.72 |
| influence | 138 | 0 | 0.4100 | 0.4343 | 0.1128 | 5.36 |
| fairness | 3 | 0 | 0.3546 | 0.2745 | 0.1707 | 5.63 |
| drift | 60 | 0 | 0.0756 | 0.0759 | 0.0345 | 2.18 |
| interventions | 3 | 0 | 2.9106 | 2.7874 | 0.3602 | 5.92 |
| performance | 30 | 0 | 5.9734 | 2.5659 | 8.6977 | 43.16 |
