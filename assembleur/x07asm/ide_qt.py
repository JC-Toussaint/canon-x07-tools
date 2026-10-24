"""Éditeur-débogueur visuel du X-07, version Qt (PyQt6).

Même logique que l'éditeur tkinter (ide.Session : compilation, points
d'arrêt, pas à pas, variables) et mêmes commandes ; seule la fenêtre change :
  - éditeur avec marge (numéros, points d'arrêt, ligne en cours) ;
  - police à chasse fixe fournie par le système (QFontDatabase), partout ;
  - thème clair ou sombre suivant le système, coloration adaptée ;
  - minuteries de Qt sur l'horloge monotone : pas de gel quand l'horloge
    murale saute (WSL), sans la Cadence de la version tkinter.

Lancement : python3 x07asm.py ide --qt [programme]   (pip install PyQt6)
"""
import os
import sys
import threading
import time

from PyQt6.QtCore import QPointF, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import (QAction, QColor, QFont, QFontDatabase, QImage, QKeySequence,
                         QPainter, QPen, QPolygonF, QSyntaxHighlighter, QTextBlockUserData,
                         QTextCharFormat, QTextCursor, QTextFormat)
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                             QSplitter, QTabWidget, QTextEdit, QToolBar, QVBoxLayout, QWidget)

from . import debug, syntaxe
from .afficheur import ARROWS, BEZEL, OFF, ON, Touches, connect_speaker, release_key, send_key
from .ide import (AIDE, FLAG_NAMES, KINDS, REG_ROWS, TEMPLATES, TOOLBAR, Session,
                  SuiviRegistres)
from .lcd import HEIGHT, WIDTH

COULEURS = {   # coloration syntaxique : thème clair, thème sombre
    "clair": {"motcle": "#0033b3", "fonction": "#871094", "chaine": "#a31515",
              "commentaire": "#4f7f4f", "numero": "#8a8a8a", "directive": "#00777a",
              "registre": "#a35a00", "etiquette": "#6b3f00"},
    "sombre": {"motcle": "#7aa2f7", "fonction": "#c792ea", "chaine": "#e0a080",
               "commentaire": "#7fae7f", "numero": "#8a8a8a", "directive": "#56c8c8",
               "registre": "#e5a55a", "etiquette": "#e0c080"},
}
FONDS = {"clair": ("#fff3a8", "#ffd6d6"), "sombre": ("#5a5320", "#5a2a2a")}  # en cours, arrêt
FILTRES = ("Programmes X-07 (*.bas *.qbas *.asm);;BASIC du X-07 (*.bas);;"
           "QuickBASIC (*.qbas);;Assembleur (*.asm);;Tous (*)")

# touches de Qt -> noms de touches de tkinter (afficheur.send_key, HELD_KEYS)
QT_KEYS = {Qt.Key.Key_Return: "Return", Qt.Key.Key_Enter: "KP_Enter",
           Qt.Key.Key_Backspace: "BackSpace", Qt.Key.Key_Delete: "Delete",
           Qt.Key.Key_Insert: "Insert", Qt.Key.Key_Home: "Home", Qt.Key.Key_Escape: "Escape",
           Qt.Key.Key_F9: "F9", Qt.Key.Key_Space: "space", Qt.Key.Key_Clear: "KP_Begin",
           Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right", Qt.Key.Key_Up: "Up",
           Qt.Key.Key_Down: "Down"}
FLECHES = ("Left", "Right", "Up", "Down")


class Touche:
    """Une touche de Qt vue comme un événement de tkinter (keysym, char)."""

    def __init__(self, keysym, char=""):
        self.keysym, self.char = keysym, char


def touche_qt(ev):
    """QKeyEvent -> Touche : flèches du pavé numérique (verrou éteint)
    distinguées (KP_Up...), comme dans la fenêtre tkinter."""
    sym = QT_KEYS.get(Qt.Key(ev.key()), ev.text())
    if sym in FLECHES and ev.modifiers() & Qt.KeyboardModifier.KeypadModifier:
        sym = "KP_" + sym
    return Touche(sym, ev.text())


def sombre(app):
    return app.palette().window().color().lightness() < 128


# -------------------------------------------------------------- écran et pavé
class EcranQt(QWidget):
    """L'écran du X-07 (120 x 32 points), curseur clignotant ; il reçoit le
    clavier quand on clique dessus (cadre vert)."""

    def __init__(self, editeur, zoom=3):
        super().__init__()
        self.editeur, self.zoom, self.pad = editeur, zoom, 4 * zoom
        self.setFixedSize(WIDTH * zoom + 2 * self.pad, HEIGHT * zoom + 2 * self.pad)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.image = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB32)
        self.image.fill(QColor(OFF))
        self._last, self._blink, self._blink_t = None, True, 0

    def refresh(self, lcd):
        """Redessine si l'écran (ou le clignotement du curseur) a changé."""
        now = time.monotonic()
        if now - self._blink_t > 0.4:
            self._blink, self._blink_t = not self._blink, now
        key = (lcd.version, lcd.cursor is not None and self._blink)
        if key == self._last:
            return
        self._last = key
        on, off = QColor(ON).rgb(), QColor(OFF).rgb()
        for y, row in enumerate(lcd.rows_bits(cursor=key[1])):
            for x, b in enumerate(row):
                self.image.setPixel(x, y, on if b else off)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BEZEL))
        p.drawImage(QRect(self.pad, self.pad, WIDTH * self.zoom, HEIGHT * self.zoom), self.image)
        p.setPen(QPen(QColor("#2c9a3c" if self.hasFocus() else "#111"), 3))
        p.drawRect(self.rect().adjusted(1, 1, -2, -2))

    def keyPressEvent(self, ev):
        self.editeur.screen_key(touche_qt(ev))

    def keyReleaseEvent(self, ev):
        if not ev.isAutoRepeat():
            self.editeur.screen_key_release(touche_qt(ev))

    def focusInEvent(self, ev):
        self.editeur.show_focus(True)
        self.update()

    def focusOutEvent(self, ev):
        self.editeur.show_focus(False)
        self.update()

    def focusNextPrevChild(self, nxt):
        return False                       # Tab va au X-07, pas au widget suivant


class PaveQt(QWidget):
    """Le pavé de flèches du X-07 : quatre flèches et un bouton au milieu,
    tenus tant que le bouton de la souris est enfoncé (STICK, STRIG(1))."""

    KEY, KEY_DOWN, EDGE, MARK = "#d8d8d4", "#8f8f8a", "#55554f", "#2b2b2e"
    TIPS = {"haut": "flèche haut (STICK 1)", "bas": "flèche bas (STICK 5)",
            "gauche": "flèche gauche (STICK 7)", "droite": "flèche droite (STICK 3)",
            "milieu": "bouton du milieu (F6, STRIG(1))"}

    def __init__(self, touches, size=120):
        super().__init__()
        self.touches = touches
        touches.on_change = self.update
        self.setFixedSize(size, size)
        self.setMouseTracking(True)
        # comme sur la machine : quatre touches trapézoïdales autour d'un bouton carré
        lo, hi, gap = 3, size - 3, max(2, size // 30)
        inner = size * 0.32
        p, q = (size - inner) / 2, (size + inner) / 2
        place = {"haut": lambda x, y: (x, y), "bas": lambda x, y: (x, size - y),
                 "gauche": lambda x, y: (y, x), "droite": lambda x, y: (size - y, x)}
        trap = ((lo + gap, lo), (hi - gap, lo), (q, p - gap), (p, p - gap))
        cx, cy, r = size / 2, (lo + p - gap) / 2, size / 14
        tri = ((cx, cy - r), (cx - r, cy + 0.7 * r), (cx + r, cy + 0.7 * r))
        poly = lambda pts: QPolygonF([QPointF(x, y) for x, y in pts])   # noqa: E731
        self.keys = {n: (poly(f(x, y) for x, y in trap), poly(f(x, y) for x, y in tri))
                     for n, f in place.items()}
        self.keys["milieu"] = (poly(((p, p), (q, p), (q, q), (p, q))), None)
        self.mouse = None

    def name_at(self, pos):
        pt = QPointF(pos)
        return next((n for n, (k, _) in self.keys.items()
                     if k.containsPoint(pt, Qt.FillRule.OddEvenFill)), None)

    def click(self, name):
        self.mouse = name
        self.touches.press((name,), ARROWS.get(name), 6 if name == "milieu" else None)

    def unclick(self):
        if self.mouse:
            self.touches.release((self.mouse,))
            self.mouse = None

    def mousePressEvent(self, ev):
        name = self.name_at(ev.position())
        if name:
            self.click(name)

    def mouseReleaseEvent(self, ev):
        self.unclick()

    def mouseMoveEvent(self, ev):
        name = self.name_at(ev.position())
        self.setToolTip(self.TIPS.get(name, ""))

    def paintEvent(self, event):
        m = self.touches.get_m()
        held = m.held if m is not None else set()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for name, (key, mark) in self.keys.items():
            p.setPen(QPen(QColor(self.EDGE), 2))
            p.setBrush(QColor(self.KEY_DOWN if name in held else self.KEY))
            p.drawPolygon(key)
            if mark is not None:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(self.MARK))
                p.drawPolygon(mark)


class RegistresQt(QFrame):
    """Les registres du Z80 en cases (nom en petit, valeur en gros), en
    couleur s'ils ont changé depuis l'arrêt précédent ; les indicateurs en
    pastilles allumées ou éteintes, expliquées au survol."""

    TEINTES = {"clair": ("#c45a00", "#fff1d6"), "sombre": ("#ffb86c", "#4a3a1e")}

    def __init__(self, font, theme):
        super().__init__()
        self.setObjectName("registres")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.change, self.fond_change = self.TEINTES[theme]
        self.suivi = SuiviRegistres()
        self.digits = {n: d for row in REG_ROWS for n, d in row}
        grid = QGridLayout(self)
        grid.setContentsMargins(10, 6, 10, 6)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(2)
        gros = QFont(font)
        gros.setPointSize(font.pointSize() + 2)
        gros.setBold(True)
        self.values = {}
        for r, row in enumerate(REG_ROWS):
            for c, (name, _) in enumerate(row):
                nom = QLabel(name)
                nom.setStyleSheet("color: palette(mid); font-size: 8pt;")
                val = QLabel()
                val.setFont(gros)
                val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                left = Qt.AlignmentFlag.AlignLeft       # surlignage à la taille de la valeur
                grid.addWidget(nom, 2 * r, c, left)
                grid.addWidget(val, 2 * r + 1, c, left)
                self.values[name] = val
        line = QHBoxLayout()
        line.setSpacing(4)
        self.flags = {}
        for n, _ in debug.FLAGS:
            lab = QLabel(n)
            lab.setFont(font)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setFixedSize(24, 20)
            lab.setToolTip(FLAG_NAMES[n])
            line.addWidget(lab)
            self.flags[n] = lab
        line.addSpacing(10)
        self.steps = QLabel()
        self.steps.setStyleSheet("color: palette(mid);")
        line.addWidget(self.steps)
        line.addStretch(1)
        grid.addLayout(line, 2 * len(REG_ROWS), 0, 1, 5)
        self.show_values(None)

    def show_values(self, vals):
        """vals : Session.register_values(), ou None (programme non compilé)."""
        changed = self.suivi.changed(vals) if vals else set()
        for name, lab in self.values.items():
            d = self.digits[name]
            lab.setText("-" * d if vals is None else "%0*X" % (d, vals[name]))
            lab.setStyleSheet("color: %s; background: %s; border-radius: 3px; padding: 0 2px;"
                              % (self.change, self.fond_change) if name in changed
                              else "padding: 0 2px;")
        f = vals["F"] if vals else 0
        for n, bit in debug.FLAGS:
            self.flags[n].setStyleSheet(
                "border-radius: 4px; font-weight: bold; "
                + ("background: #2c9a3c; color: white;" if f & bit else
                   "border: 1px solid palette(mid); color: palette(mid);"))
        self.steps.setText("(programme non compilé)" if vals is None
                           else "%s instructions" % format(vals["steps"], ",").replace(",", " "))


# -------------------------------------------------------------- éditeur de source
class Arret(QTextBlockUserData):
    """Marque de point d'arrêt sur une ligne : elle suit le texte édité."""


class Coloration(QSyntaxHighlighter):
    def __init__(self, doc, theme):
        super().__init__(doc)
        self.kind = ""
        self.formats = {}
        for cat, color in COULEURS[theme].items():
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if cat == "commentaire":
                f.setFontItalic(True)
            elif cat == "etiquette":
                f.setFontWeight(QFont.Weight.Bold)
            self.formats[cat] = f

    def highlightBlock(self, text):
        for cat, _, a, b in syntaxe.zones(text, self.kind):
            self.setFormat(a, b - a, self.formats[cat])


class Marge(QWidget):
    """Numéros de ligne, points d'arrêt (rouge) et ligne en cours (▶)."""

    def __init__(self, source):
        super().__init__(source)
        self.source = source

    def sizeHint(self):
        return QSize(self.source.marge_largeur(), 0)

    def paintEvent(self, event):
        self.source.peindre_marge(event)

    def mousePressEvent(self, ev):
        block = self.source.cursorForPosition(QPointF(0, ev.position().y()).toPoint()).block()
        self.source.marge_clic(block.blockNumber() + 1)


class Source(QPlainTextEdit):
    """Le texte du programme, avec sa marge."""

    def __init__(self, editeur, font):
        super().__init__()
        self.editeur = editeur
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(8 * self.fontMetrics().horizontalAdvance(" "))
        self.marge = Marge(self)
        self.blockCountChanged.connect(lambda _: self.setViewportMargins(self.marge_largeur(),
                                                                         0, 0, 0))
        self.updateRequest.connect(self._defile)
        self.setViewportMargins(self.marge_largeur(), 0, 0, 0)

    def marge_largeur(self):
        chiffres = max(3, len(str(self.blockCount())))
        return 30 + self.fontMetrics().horizontalAdvance("9") * chiffres

    def _defile(self, rect, dy):
        if dy:
            self.marge.scroll(0, dy)
        else:
            self.marge.update(0, rect.y(), self.marge.width(), rect.height())

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        r = self.contentsRect()
        self.marge.setGeometry(QRect(r.left(), r.top(), self.marge_largeur(), r.height()))

    def marge_clic(self, line):
        self.editeur.gutter_click(line)

    def peindre_marge(self, event):
        e = self.editeur
        p = QPainter(self.marge)
        pal = self.palette()
        p.fillRect(event.rect(), pal.alternateBase())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = e.session
        current = s.current_line() if (s and s.m and not e.busy()) else None
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        h = self.fontMetrics().height()
        w = self.marge.width()
        while block.isValid() and top <= event.rect().bottom():
            line = block.blockNumber() + 1
            mid = top + h // 2
            if isinstance(block.userData(), Arret):
                p.setPen(QColor("#900"))
                p.setBrush(QColor("#d22"))
                p.drawEllipse(QPointF(10, mid), 5, 5)
            if line == current:
                p.setPen(QColor("#c80"))
                p.drawText(QRect(16, top, 14, h), Qt.AlignmentFlag.AlignCenter, "▶")
            p.setPen(pal.placeholderText().color())
            p.drawText(QRect(0, top, w - 6, h), Qt.AlignmentFlag.AlignRight, str(line))
            top += round(self.blockBoundingRect(block).height())
            block = block.next()


# -------------------------------------------------------------- la fenêtre
class Editeur(QMainWindow):
    """La fenêtre de l'éditeur-débogueur (mêmes commandes que ide.Editeur)."""

    def __init__(self, path=None, ram=16, zoom=3, memoire=None, muet=False):
        self.app = QApplication.instance() or QApplication(sys.argv[:1])
        super().__init__()
        from .son import HautParleur
        self.memoire = memoire
        self.hp = HautParleur(muet)
        self.ram = ram
        self.session = None
        self.path = None
        self.worker = None
        self.dirty = False
        self.previous = {}                       # variable -> valeur à l'arrêt précédent
        self.theme = "sombre" if sombre(self.app) else "clair"
        self.mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.mono.setPointSize(10)
        self.setWindowTitle("Canon X-07 : éditeur-débogueur")
        self.resize(1250, 760)

        self.actions = {}
        self.build_actions()
        self.build_menus()
        bar = QToolBar("Exécution")
        bar.setMovable(False)
        bar.setStyleSheet("QToolButton { font-size: 16px; min-width: 28px; }")
        for key, symbol, tip, cmd in TOOLBAR:
            if key is None:
                bar.addSeparator()
            else:
                bar.addAction(self.actions[key])
        self.addToolBar(bar)
        self.toolbar = bar
        self.status = QLabel("")
        self.statusBar().addWidget(self.status, 1)

        panes = QSplitter(Qt.Orientation.Horizontal)
        self.text = Source(self, self.mono)
        self.coloration = Coloration(self.text.document(), self.theme)
        self.text.document().contentsChanged.connect(self.on_modified)
        panes.addWidget(self.text)

        right = QWidget()
        col = QVBoxLayout(right)
        col.setContentsMargins(6, 4, 4, 4)
        self.screen_hint = QLabel()
        col.addWidget(self.screen_hint)
        row = QHBoxLayout()                       # l'écran, et le pavé de flèches du X-07
        self.ecran = EcranQt(self, zoom)
        self.touches = Touches(None, self.running_machine)
        self.pave = PaveQt(self.touches, size=self.ecran.height())
        row.addWidget(self.ecran)
        row.addSpacing(14)
        row.addWidget(self.pave)
        row.addStretch(1)
        col.addLayout(row)
        line = QHBoxLayout()                      # saisie sûre : une ligne, puis Entrée
        line.addWidget(QLabel("Taper pour le X-07 :"))
        self.entry = QLineEdit()
        self.entry.setFont(self.mono)
        self.entry.setMaximumWidth(220)
        self.entry.returnPressed.connect(self.send_line)
        line.addWidget(self.entry)
        send = QPushButton("Envoyer ⏎")
        send.clicked.connect(self.send_line)
        line.addWidget(send)
        line.addStretch(1)
        col.addLayout(line)
        titre = QLabel("Registres")
        titre.setStyleSheet("font-weight: bold;")
        col.addWidget(titre)
        self.regs = RegistresQt(self.mono, self.theme)
        col.addWidget(self.regs)
        self.tabs = QTabWidget()
        self.panels = {}
        for key, title in (("variables", "Variables"), ("code", "Code machine"),
                           ("pile", "Pile"), ("messages", "Messages")):
            t = QPlainTextEdit()
            t.setReadOnly(True)
            t.setFont(self.mono)
            t.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            self.tabs.addTab(t, title)
            self.panels[key] = t
        col.addWidget(self.tabs, 1)
        panes.addWidget(right)
        panes.setStretchFactor(0, 3)
        panes.setStretchFactor(1, 2)
        panes.setSizes([760, 490])
        self.setCentralWidget(panes)
        self.show_focus(False)

        if path:
            self.load(path)
        self.update_buttons()
        self.timer = QTimer(self)                 # horloge monotone (pas de gel sous WSL)
        self.timer.timeout.connect(self.tick)
        self.timer.start(40)
        self.show()

    # -------------------------------------------------- actions, menus
    def build_actions(self):
        cmds = {key: (symbol, tip, cmd) for key, symbol, tip, cmd in TOOLBAR if key}
        keys = {"continuer": "F5", "ligne": "F10", "entrer": "F11", "sortir": "Shift+F11"}
        for key, (symbol, tip, cmd) in cmds.items():
            a = QAction(symbol, self)
            a.setToolTip(tip)
            a.triggered.connect(lambda _=False, c=cmd: getattr(self, c[0])(*c[1:]))
            if key in keys:
                a.setShortcut(QKeySequence(keys[key]))
            self.actions[key] = a
        f9 = QAction("Point d'arrêt / pause", self)  # F9 : dans le source, point d'arrêt
        f9.setShortcut(QKeySequence("F9"))
        f9.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        f9.triggered.connect(self.f9)
        self.addAction(f9)

    def build_menus(self):
        mb = self.menuBar()
        self.menu_items = []                      # (action, clé d'état)

        def add(menu, label, cmd, key, accel=None):
            a = menu.addAction(label)
            a.triggered.connect(lambda _=False: cmd())
            if accel:
                a.setShortcut(QKeySequence(accel))
            self.menu_items.append((a, key))
            return a

        fichier = mb.addMenu("&Fichier")
        nouveau = fichier.addMenu("Nouveau")
        for ext, label in KINDS:
            a = nouveau.addAction("%s (%s)" % (label, ext))
            a.triggered.connect(lambda _=False, e=ext: self.new_dialog(e))
        self.menu_items.append((nouveau.menuAction(), "nouveau"))
        add(fichier, "Ouvrir…", self.open_dialog, "ouvrir", "Ctrl+O")
        add(fichier, "Enregistrer", self.save, "enregistrer", "Ctrl+S")
        add(fichier, "Enregistrer sous…", self.save_as_dialog, "enregistrer_sous", "Ctrl+Shift+S")
        fichier.addSeparator()
        fichier.addAction("Quitter").triggered.connect(self.close)

        execution = mb.addMenu("&Exécution")
        labels = {"compiler": "Compiler", "continuer": "Continuer", "pause": "Pause\tF9",
                  "ligne": "Ligne suivante", "entrer": "Entrer dans la procédure",
                  "sortir": "Sortir de la procédure", "instr": "Une instruction machine",
                  "reinit": "Recommencer"}
        for key, symbol, tip, cmd in TOOLBAR:
            if key is None:
                execution.addSeparator()
                continue
            a = self.actions[key]
            item = QAction("%s  %s" % (symbol, labels[key]), self)
            item.setShortcut(a.shortcut())
            if key == "pause":
                item.setText("%s  Pause\tF9" % symbol)
            item.triggered.connect(a.trigger)
            a.setShortcut(QKeySequence())          # le raccourci passe au menu
            execution.addAction(item)
            self.menu_items.append((item, key))
        add(execution, "Enlever tous les points d'arrêt", self.clear_breaks, "reinit")

        aide = mb.addMenu("&Aide")
        aide.addAction("Utilisation…").triggered.connect(self.show_help)
        self.menubar = mb

    def show_help(self):
        QMessageBox.information(self, "Aide", AIDE)

    def clear_breaks(self):
        if self.session is None:
            return
        for line in list(self.session.break_lines):
            self.session.toggle_break(line)
        self.sync_text_from_breaks()
        self.refresh()

    # -------------------------------------------------- fichier
    def open_dialog(self):
        if self.busy() or not self.confirm_discard():
            return
        p, _ = QFileDialog.getOpenFileName(self, "Ouvrir", "", FILTRES)
        if p:
            self.load(p)

    def modified(self):
        return self.text.document().isModified()

    def confirm_discard(self):
        """Modifications non enregistrées : proposer de les enregistrer.
        Rend False si l'utilisateur annule."""
        if not (self.path and self.modified()):
            return True
        B = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self, "Modifications", "Enregistrer les modifications de %s ?"
            % os.path.basename(self.path), B.Save | B.Discard | B.Cancel)
        if answer == B.Cancel:
            return False
        if answer == B.Save:
            self.save()
        return True

    def new_dialog(self, ext):
        if self.busy() or not self.confirm_discard():
            return
        label = dict(KINDS)[ext]
        p, _ = QFileDialog.getSaveFileName(self, "Nouveau programme : %s" % label,
                                           "nouveau" + ext, "%s (*%s);;Tous (*)" % (label, ext))
        if p:
            if not os.path.splitext(p)[1]:
                p += ext
            self.new_file(p)

    def new_file(self, path):
        """Crée le programme (modèle selon l'extension) et l'ouvre."""
        ext = os.path.splitext(path)[1].lower()
        if ext not in TEMPLATES:
            self.set_status("extension inconnue : .bas, .qbas ou .asm")
            return False
        with open(path, "w", encoding="utf-8") as f:
            f.write(TEMPLATES[ext])
        self.load(path)
        self.set_status("nouveau programme %s : modifiez-le, puis ▶" % os.path.basename(path))
        return True

    def save_as_dialog(self):
        if not self.path or self.busy():
            return
        p, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", os.path.abspath(self.path),
                                           FILTRES)
        if p:
            self.save_as(p)

    def save_as(self, path):
        """Enregistre le texte sous un autre nom, qui devient le fichier ouvert
        (les points d'arrêt sont gardés ; à recompiler)."""
        if os.path.splitext(path)[1].lower() not in TEMPLATES:
            self.set_status("extension inconnue : .bas, .qbas ou .asm")
            return False
        if self.session is not None:
            self.sync_breaks_from_text()
            breaks = set(self.session.break_lines)
        else:
            breaks = set()
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.text.toPlainText())
        self.path = path
        self.session = Session(path, self.ram, self.memoire,
                               self.session.image if self.session else None)
        self.session.break_lines = breaks
        self.coloration.kind = os.path.splitext(path)[1].lower().lstrip(".")
        self.coloration.rehighlight()
        self.text.document().setModified(False)
        self.dirty = True
        self.set_title()
        self.set_status("enregistré sous %s" % path)
        self.refresh()
        return True

    def load(self, path):
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        self.path = path
        self.session = Session(path, self.ram, self.memoire,
                               self.session.image if self.session else None)
        self.coloration.kind = os.path.splitext(path)[1].lower().lstrip(".")
        self.text.setPlainText(content)           # recolore, vide l'historique d'annulation
        self.text.document().setModified(False)
        self.dirty = False
        self.set_title()
        self.set_status("%s ouvert : Compiler, puis ▶" % os.path.basename(path))
        self.refresh()

    def save(self):
        if not self.path:
            return False
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(self.text.toPlainText())
        self.text.document().setModified(False)
        self.dirty = True                         # à recompiler
        self.set_title()
        self.set_status("enregistré")
        return True

    def set_title(self):
        name = os.path.basename(self.path or "?")
        self.setWindowTitle("Canon X-07 : %s%s" % (name, " *" if self.modified() else ""))

    def on_modified(self):
        if self.modified():
            self.dirty = True
            self.set_title()
            if self.session:
                self.sync_breaks_from_text()

    # -------------------------------------------------- compilation
    def compile(self):
        if not self.path or self.busy():
            return False
        if self.modified():
            self.save()
        self.set_title()
        self.sync_breaks_from_text()              # après d'éventuelles modifications
        try:
            warns = self.session.build()
            connect_speaker(self.session.m, self.hp)
        except Exception as e:                    # erreur de compilation : on l'affiche
            self.session.m = None
            self.set_status("erreur : %s" % e)
            self.show_text("messages", "erreur : %s" % e)
            self.tabs.setCurrentWidget(self.panels["messages"])
            self.refresh()
            return False
        self.dirty = False
        self.previous = {}
        self.regs.suivi.reset()
        self.sync_text_from_breaks()              # déplacés sur une ligne avec du code
        self.show_text("messages", "\n".join("attention : %s" % w for w in warns)
                       or "compilé sans avertissement")
        self.set_status("compilé : %d point(s) d'arrêt ; ▶ pour lancer"
                        % len(self.session.break_lines))
        self.refresh()
        return True

    def restart(self):
        if self.busy():
            self.do_pause()
            return
        self.compile()

    def ready(self):
        """Compile si nécessaire ; rend True si l'on peut exécuter."""
        if self.session is None:
            return False
        if self.session.m is None or self.dirty:
            return self.compile()
        return True

    # -------------------------------------------------- exécution (fil séparé)
    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    def start(self, action, label):
        if self.busy() or not self.ready():
            return
        if self.session.finished:
            self.set_status("programme terminé : ↺ pour recommencer")
            return
        self.set_status(label)
        self.ecran.setFocus()                     # le clavier va au X-07

        def work():
            try:
                action()
            except Exception as e:                # erreur inattendue : affichée
                self.session.reason = "erreur : %s" % e
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self.refresh_marks()
        self.update_buttons()

    def do_run(self):
        self.start(lambda: self.session.run(), "en cours… (‖ ou F9 pour arrêter)")

    def do_step(self, how):
        s = self.session
        if s is None:
            return
        actions = {"over": lambda: s.step_line(True), "into": lambda: s.step_line(False),
                   "out": s.finish, "instr": s.step_instruction}
        self.start(actions[how], "pas à pas…")

    def do_pause(self):
        if self.session:
            self.session.pause()

    def f9(self):
        if self.text.hasFocus():                  # F9 dans le source : point d'arrêt
            self.toggle(self.text.textCursor().blockNumber() + 1)
        else:
            self.do_pause()

    # -------------------------------------------------- points d'arrêt
    def gutter_click(self, line):
        if self.session is not None:
            self.toggle(line)

    def sync_breaks_from_text(self):
        """Les points d'arrêt suivent le texte édité (marques sur les lignes)."""
        lines, block = set(), self.text.document().firstBlock()
        while block.isValid():
            if isinstance(block.userData(), Arret):
                lines.add(block.blockNumber() + 1)
            block = block.next()
        self.session.break_lines = lines

    def sync_text_from_breaks(self):
        doc = self.text.document()
        block = doc.firstBlock()
        while block.isValid():
            block.setUserData(Arret() if block.blockNumber() + 1 in self.session.break_lines
                              else None)
            block = block.next()
        self.text.marge.update()

    def toggle(self, line):
        if self.session is None:
            return
        if self.session.m is None or self.dirty:
            self.sync_breaks_from_text()          # pas encore compilé : ligne telle quelle
        got, on = self.session.toggle_break(line)
        self.sync_text_from_breaks()
        if got is None:
            self.set_status("pas de code à partir de la ligne %d" % line)
        elif got != line and on:
            self.set_status("point d'arrêt sur la ligne %d (première ligne avec du code)" % got)
        self.refresh()

    # -------------------------------------------------- affichage
    def set_status(self, text):
        self.status.setText(text)

    def show_text(self, key, text):
        self.panels[key].setPlainText(text)

    def show_variables(self, lines):
        """Variables ; en rouge, celles qui ont changé depuis l'arrêt précédent."""
        t = self.panels["variables"]
        t.setPlainText("\n".join(lines) or "(aucune)")
        rouge = QTextCharFormat()
        rouge.setForeground(QColor("#ff6b6b" if self.theme == "sombre" else "#c00000"))
        now = {}
        for k, line in enumerate(lines):
            name, _, val = line.partition(" = ")
            now[name] = val
            if name in self.previous and self.previous[name] != val:
                c = QTextCursor(t.document().findBlockByNumber(k))
                c.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                               QTextCursor.MoveMode.KeepAnchor)
                c.setCharFormat(rouge)
        self.previous = now

    def refresh_marks(self):
        """Fonds des lignes : points d'arrêt, et ligne en cours (machine arrêtée)."""
        s = self.session
        en_cours, arret = FONDS[self.theme]
        sel = []

        def fond(line, color):
            block = self.text.document().findBlockByNumber(line - 1)
            if not block.isValid():
                return
            x = QTextEdit.ExtraSelection()
            x.format.setBackground(QColor(color))
            x.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            x.cursor = QTextCursor(block)
            sel.append(x)
        if s:
            for line in sorted(s.break_lines):
                fond(line, arret)
            if s.m and not self.busy():
                cur = s.current_line()
                if cur:
                    fond(cur, en_cours)
                    self.see_line(cur)
        self.text.setExtraSelections(sel)
        self.text.marge.update()

    def see_line(self, line):
        bar = self.text.verticalScrollBar()       # sans retour à la ligne : 1 cran = 1 ligne
        shown = max(1, self.text.viewport().height() // self.text.fontMetrics().lineSpacing())
        if not bar.value() <= line - 1 < bar.value() + shown:
            bar.setValue(max(0, line - 1 - shown // 3))

    def refresh(self):
        """Met à jour la source, les registres et les onglets (machine arrêtée)."""
        s = self.session
        if s and self.dirty:
            self.sync_breaks_from_text()
        self.refresh_marks()
        if s and s.m and not self.busy():
            self.regs.show_values(s.register_values())
            self.show_variables(s.variables())
            self.show_text("code", s.disassembly())
            self.show_text("pile", s.stack())
        elif not (s and s.m):
            self.regs.show_values(None)
        self.update_buttons()

    def state_of(self, key):
        run = self.busy()
        if key == "pause":
            return run
        if key in ("ouvrir", "nouveau"):
            return not run
        return self.session is not None and not run

    def update_buttons(self):
        for key, a in self.actions.items():
            a.setEnabled(self.state_of(key))
        for a, key in getattr(self, "menu_items", []):
            a.setEnabled(self.state_of(key))

    def tick(self):
        self.touches.poll()
        s = self.session
        if s and s.m:
            self.ecran.refresh(s.m.lcd)
        if self.worker is not None and not self.worker.is_alive():
            self.worker = None
            reason = s.reason
            if s.finished:
                saved = s.save_memory()
                self.set_status("programme terminé (%s)%s : ↺ pour recommencer"
                                % (reason or "fin",
                                   "" if not saved else " ; mémoire enregistrée (OFF)"
                                   if s.memoire else " ; fichiers en RAM gardés"))
            else:
                line = s.current_line()
                self.set_status("arrêt%s%s" % (" : %s" % reason if reason else "",
                                               ", ligne %d" % line if line else ""))
            if s.messages:
                self.show_text("messages", "\n".join(s.messages[-50:]))
            self.refresh()
        elif self.busy() and s and s.m:
            if s.m.lcd.cursor is not None:
                self.set_status("le X-07 attend une touche : cliquez sur l'écran et tapez")

    def show_focus(self, on):
        self.screen_hint.setText("Écran du X-07 : le clavier va au X-07 (Échap = BREAK)" if on
                                 else "Écran du X-07 : cliquez dessus pour taper, "
                                      "ou utilisez le champ dessous")
        self.screen_hint.setStyleSheet("color: %s;" % ("#2c9a3c" if on else "palette(mid)"))

    def screen_key(self, ev):
        """Touche tapée sur l'écran.  Programme arrêté : la touche est gardée,
        le programme la lira en repartant."""
        s = self.session
        if s and s.m and not s.finished:
            before = len(s.m.keys)
            send_key(s.m, ev, self.touches)
            if not self.busy() and len(s.m.keys) > before:
                self.set_status("touches gardées pour le programme : %r ; ▶ pour continuer"
                                % "".join(s.m.keys))
        elif s and s.finished:
            self.set_status("programme terminé : ↺ pour recommencer, puis tapez")

    def screen_key_release(self, ev):
        release_key(ev, self.touches)

    def running_machine(self):
        """Machine du programme (pour le pavé de flèches), None s'il n'y en a pas."""
        s = self.session
        return s.m if s is not None and s.m is not None and not s.finished else None

    def send_line(self):
        """Champ « Taper pour le X-07 » : le texte tel quel, puis Entrée."""
        s = self.session
        text = self.entry.text()
        if not (s and s.m) or s.finished:
            self.set_status("lancez d'abord le programme (▶)")
            return
        s.m.keys += list(text) + ["\r"]
        self.entry.clear()
        if not self.busy():
            self.set_status("ligne gardée pour le programme : %r ; ▶ pour continuer" % text)

    def closeEvent(self, ev):
        if not self.confirm_discard():
            ev.ignore()
            return
        if self.session and self.session.m:
            self.session.m.stop_requested = True
        self.timer.stop()
        self.hp.close()
        ev.accept()

    def mainloop(self):
        self.app.exec()
