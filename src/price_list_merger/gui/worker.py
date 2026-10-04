"""Свод в отдельном потоке, чтобы окно не «зависало» на больших прайсах."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from ..core.loader import PriceListError
from ..core.merging import MergeSettings
from ..core.pipeline import MergeReport, SupplierSource, run_merge
from ..core.pricing import PricingSettings


class MergeWorker(QThread):
    progress = pyqtSignal(int, str)  # проценты и текст
    done = pyqtSignal(object)  # MergeReport
    failed = pyqtSignal(str)

    def __init__(
        self,
        sources: list[SupplierSource],
        merge_settings: MergeSettings,
        pricing: PricingSettings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.sources = sources
        self.merge_settings = merge_settings
        self.pricing = pricing

    def run(self) -> None:
        try:
            report: MergeReport = run_merge(
                self.sources, self.merge_settings, self.pricing,
                progress=lambda share, text: self.progress.emit(int(share * 100), text),
            )
        except PriceListError as error:
            self.failed.emit(str(error))
        except Exception as error:  # неожиданная ошибка не должна ронять окно
            self.failed.emit(f"Непредвиденная ошибка: {error!r}")
        else:
            self.done.emit(report)
