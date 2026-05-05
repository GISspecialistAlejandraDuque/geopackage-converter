"""
QGIS plugin entry point for GeoPackage Converter.

Registers:
  * a menu action under Vector > GeoPackage Converter
  * a toolbar button on the main toolbar
  * the Processing provider (two algorithms)
  * a QTranslator for it/en/es localisation, picked from QGIS locale
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from qgis.core import QgsApplication, QgsMessageLog
from qgis.PyQt.QtCore import QCoreApplication, QLocale, QSettings, QTranslator
from qgis.PyQt.QtGui import QIcon

from .compat import QAction
from .gui.main_dialog import GeoPackageConverterDialog
from .processing.provider import GeoPackageConverterProvider

LOG_TAG = "GeoPackage Converter"
PLUGIN_DIR = Path(__file__).resolve().parent
ICON_PATH = PLUGIN_DIR / "resources" / "icons" / "icon.svg"


class GeoPackageConverterPlugin:
    """Main plugin class instantiated by `classFactory(iface)`."""

    MENU_NAME = "&GeoPackage Converter"
    TOOLBAR_NAME = "GeoPackage Converter"

    def __init__(self, iface) -> None:
        self.iface = iface
        self._actions: list = []
        self._toolbar = None
        self._provider: Optional[GeoPackageConverterProvider] = None
        self._translator: Optional[QTranslator] = None
        self._dialog: Optional[GeoPackageConverterDialog] = None

        self._install_translator()

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def _install_translator(self) -> None:
        """Load the .qm file matching the QGIS locale, if available."""
        override = QSettings().value("locale/userLocale") or QLocale().name()
        locale = (override or "")[:2].lower()
        if locale == "it":
            return  # Italian is the source language — no translation needed.
        qm_path = PLUGIN_DIR / "i18n" / f"geopackage_converter_{locale}.qm"
        if not qm_path.is_file():
            return
        translator = QTranslator()
        if translator.load(str(qm_path)):
            QCoreApplication.installTranslator(translator)
            self._translator = translator
            QgsMessageLog.logMessage(f"Loaded translation: {qm_path.name}", LOG_TAG)

    @staticmethod
    def tr(message: str) -> str:
        """Translate a string using the plugin's translation context."""
        return QCoreApplication.translate("GeoPackageConverterPlugin", message)

    # ------------------------------------------------------------------
    # QGIS plugin lifecycle
    # ------------------------------------------------------------------

    def initGui(self) -> None:  # noqa: N802 - QGIS API
        icon = QIcon(str(ICON_PATH)) if ICON_PATH.is_file() else QIcon()

        # Toolbar
        self._toolbar = self.iface.addToolBar(self.TOOLBAR_NAME)
        self._toolbar.setObjectName("GeoPackageConverterToolbar")

        # Main action
        action = QAction(icon, self.tr("Apri GeoPackage Converter"), self.iface.mainWindow())
        action.setObjectName("geopackageConverterOpen")
        action.setStatusTip(self.tr("Converti file vettoriali in GeoPackage"))
        action.triggered.connect(self.run)
        self._toolbar.addAction(action)
        self.iface.addPluginToVectorMenu(self.MENU_NAME, action)
        self._actions.append(action)

        # Processing provider
        self._provider = GeoPackageConverterProvider()
        QgsApplication.processingRegistry().addProvider(self._provider)

        QgsMessageLog.logMessage("Plugin initialised", LOG_TAG)

    def unload(self) -> None:
        for action in self._actions:
            try:
                self.iface.removePluginVectorMenu(self.MENU_NAME, action)
            except Exception:  # noqa: BLE001
                pass
            try:
                if self._toolbar is not None:
                    self._toolbar.removeAction(action)
            except Exception:  # noqa: BLE001
                pass
        self._actions.clear()

        if self._toolbar is not None:
            self._toolbar.deleteLater()
            self._toolbar = None

        if self._provider is not None:
            QgsApplication.processingRegistry().removeProvider(self._provider)
            self._provider = None

        if self._translator is not None:
            QCoreApplication.removeTranslator(self._translator)
            self._translator = None

        try:
            if self._dialog is not None:
                self._dialog.close()
        except RuntimeError:
            pass
        self._dialog = None

        QgsMessageLog.logMessage("Plugin unloaded", LOG_TAG)

    # ------------------------------------------------------------------
    # Action handler
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Open (or re-show) the main dialog."""
        if self._dialog is None:
            self._dialog = GeoPackageConverterDialog(self.iface, parent=self.iface.mainWindow())
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
