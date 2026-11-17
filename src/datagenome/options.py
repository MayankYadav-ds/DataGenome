from dataclasses import dataclass
from typing import Any

from .analysis import execute
from .anomalies import AnomalyConfig
from .experiments import Intervention
from .ingestion import DatasetError
from .intelligence import IntelligenceConfig
from .leakage import LeakageConfig
from .modeling import ModelConfig
from .splits import Manifest, SplitConfig
from .univariate import UnivariateConfig
from .valuation import ValuationConfig


@dataclass
class Options:
    target: str | None = None
    strategy: str = "random"
    seed: int = 42
    group: str | None = None
    time: str | None = None
    ratios: tuple[float, float, float] = (0.6, 0.2, 0.2)
    audit_group: str | None = None
    audit_time: str | None = None
    cutoff: str | None = None
    unavailable: tuple[str, ...] = ()
    model: str = "logistic-regression"
    intervention: tuple[str, ...] = ()
    constant_feature: tuple[str, ...] = ()
    suspected_feature: tuple[str, ...] = ()
    exclude_record: tuple[int, ...] = ()
    imputation: str | None = None
    manifest: Manifest | None = None
    candidate_limit: int = 10000
    association_threshold: float = 0.9
    univariate: bool = False
    univariate_folds: int = 3
    univariate_max_features: int = 16
    univariate_minimum_score: float = 0.90
    univariate_minimum_lift: float = 0.20
    max_anomaly_rows: int = 2000
    iqr_multiplier: float = 1.5
    z_threshold: float = 3.5
    contamination: float = 0.05
    missing_warning: float = 0.05
    missing_high: float = 0.30
    max_depth: int = 8
    trees: int = 32
    valuation_method: str = "loo"
    utility: str = "accuracy"
    utility_class: str | None = None
    max_evaluations: int = 256
    permutations: int = 16
    k: int = 3
    valuation_seconds: float = 30
    removal_fraction: float = 0.1
    record_id: int | None = None
    minimum_support: int = 10
    privacy_mode: str = "detailed"
    audit_attributes: tuple[str, ...] = ()
    positive_label: str | None = None

    def run(
        self,
        operation: str,
        payload: bytes | bytearray,
        limit: int,
        rows: int,
        columns: int,
    ) -> dict[str, Any]:
        try:
            return execute(
                operation,
                payload,
                valuation=ValuationConfig(
                    self.valuation_method,
                    self.utility,
                    self.utility_class,
                    self.seed,
                    self.max_evaluations,
                    self.permutations,
                    self.k,
                    self.valuation_seconds,
                ),
                removal_fraction=self.removal_fraction,
                record_id=self.record_id,
                minimum_support=self.minimum_support,
                privacy_mode=self.privacy_mode,
                audit_attributes=self.audit_attributes,
                positive_label=self.positive_label,
                target=self.target,
                limit=limit,
                rows=rows,
                columns=columns,
                split_config=SplitConfig(
                    self.strategy, self.ratios, self.seed, self.group, self.time
                ),
                model=ModelConfig(
                    self.model, self.seed, max_depth=self.max_depth, trees=self.trees
                ),
                leakage=LeakageConfig(
                    self.audit_group,
                    self.audit_time,
                    self.cutoff,
                    self.unavailable,
                    self.candidate_limit,
                    self.association_threshold,
                    UnivariateConfig(
                        self.univariate_folds,
                        self.univariate_max_features,
                        self.univariate_minimum_score,
                        self.univariate_minimum_lift,
                    )
                    if self.univariate
                    else None,
                ),
                intervention=Intervention(
                    "remove-duplicates" in self.intervention,
                    self.constant_feature,
                    self.suspected_feature,
                    self.exclude_record,
                    self.imputation,
                ),
                manifest=self.manifest,
                intelligence=IntelligenceConfig(
                    self.missing_warning, self.missing_high, self.candidate_limit
                ),
                anomaly=AnomalyConfig(
                    self.seed,
                    self.iqr_multiplier,
                    self.z_threshold,
                    self.contamination,
                    self.max_anomaly_rows,
                ),
            )
        except ImportError as error:
            raise DatasetError(
                "dependency_unavailable",
                "A required analysis dependency could not load.",
                503,
            ) from error
