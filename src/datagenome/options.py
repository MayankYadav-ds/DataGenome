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
    max_anomaly_rows: int = 2000
    iqr_multiplier: float = 1.5
    z_threshold: float = 3.5
    contamination: float = 0.05
    missing_warning: float = 0.05
    missing_high: float = 0.30
    max_depth: int = 8
    trees: int = 32

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
