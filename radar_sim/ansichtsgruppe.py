"""Zusammengehörige Ansichten mit einer Auswahl statt weiteren Tabs wechseln."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QStackedWidget


class AnsichtsGruppe(QWidget):
    def __init__(self, ansichten: tuple[tuple[str, QWidget], ...] = ()) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        auswahl = QHBoxLayout()
        auswahl.addWidget(QLabel("Ansicht"))
        self.auswahl = QComboBox()
        self.auswahl.setMinimumContentsLength(24)
        self.auswahl.setToolTip("Wechselt die Ansicht innerhalb dieses Funktionsbereichs. Daten, Zoom und Einstellungen bleiben erhalten.")
        auswahl.addWidget(self.auswahl)
        auswahl.addStretch()
        layout.addLayout(auswahl)
        self.seiten = QStackedWidget()
        layout.addWidget(self.seiten, 1)
        self.auswahl.currentIndexChanged.connect(self.seiten.setCurrentIndex)
        for titel, widget in ansichten:
            self.add_ansicht(widget, titel)

    def add_ansicht(self, widget: QWidget, titel: str) -> None:
        self.seiten.addWidget(widget)
        self.auswahl.addItem(titel)

    def currentIndex(self) -> int:
        return self.seiten.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        self.auswahl.setCurrentIndex(index)

    def zeige(self, widget: QWidget) -> bool:
        index = self.seiten.indexOf(widget)
        if index < 0:
            return False
        self.setCurrentIndex(index)
        return True
