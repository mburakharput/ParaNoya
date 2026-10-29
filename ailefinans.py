import sys
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from PySide6.QtCore import Qt, QSize, QEventLoop, QRectF, QDate, QUrl, QEvent
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPainterPath, QColor, QFont, QPen, QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QComboBox, QStackedWidget, QFormLayout, QLineEdit, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QGroupBox, QGridLayout, QFrame, QCheckBox, QDateEdit, QScrollArea, QFileDialog, QProgressBar, QSizePolicy, QSpinBox, QCompleter, QListView)

from product_core import migrate_products, create_product, list_products, change_product, add_service, expiring, attach_product_document, list_product_documents, document_path
from recurring_core import migrate_recurring, add_item, upcoming_items, pay_occurrence, set_active
from record_manager import migrate_record_state, get_state, change_state, dependencies
from card_catalog import load_catalog, search_catalog
from bank_logo_manager import logo_path, fetch_logos
from bank_logo_renderer import bank_icon, menu_icon
from document_center import TYPES, migrate_documents, stage, list_docs, approve_salary, approve_document_entry
from kmh_core import migrate_kmh, closing_due, set_overdraft, overdraft, use_overdraft, add_installment_loan, monthly_calendar, pay_installment
from v04_core import month_add, cards,create_card,purchase,pay_card,upcoming,shared_history,edit_shared_split
from finance_core import (DB_DIR, DB_PATH, money, open_db, migrate, get_profiles, add_account,
                          add_transaction, accounts_with_balances, summary, add_member, get_members, add_shared_expense, member_expenses, transfer)


from PySide6.QtCore import QThread, Signal

def circular_mascot(path, size=60):
    """Crop the actual raster to a circle, not just its surrounding label."""
    density=3
    canvas=QPixmap(size*density,size*density)
    canvas.setDevicePixelRatio(density)
    canvas.fill(Qt.GlobalColor.transparent)
    painter=QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#ffffff'))
    painter.drawEllipse(QRectF(0,0,size,size))
    clip=QPainterPath()
    clip.addEllipse(QRectF(3,3,size-6,size-6))
    painter.setClipPath(clip)
    source=QPixmap(str(path)).scaled((size-6)*density,(size-6)*density,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
    if not source.isNull():
        width=source.width()/density;height=source.height()/density
        painter.drawPixmap(QRectF((size-width)/2,(size-height)/2,width,height),source,QRectF(source.rect()))
    painter.end()
    return canvas


class LogoDownloadWorker(QThread):
    finished_result = Signal(int, int, object)
    def run(self):
        n,p,errors = fetch_logos(timeout=5, cancelled=self.isInterruptionRequested)
        self.finished_result.emit(n,p,errors)

class FinanceBars(QWidget):
    """Real data-driven custom donut or trend painter; no chart screenshots."""
    PALETTE=['#348cff','#15cfa0','#ffac55','#ac68eb','#f45b83','#50bfe8']
    def __init__(self,title,kind='donut'):
        super().__init__()
        self.heading=title;self.kind=kind;self.values=[]
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
    def set_values(self, values):
        self.values=values;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r=self.rect().adjusted(1,1,-2,-2)
        dark=self.property('darkTheme') is True
        p.setPen(QPen(QColor('#284b66' if dark else '#dceaf6'),1));p.setBrush(QColor('#122e49' if dark else '#f8fcff'))
        p.drawRoundedRect(r,16,16)
        p.setPen(QColor('#edf8ff' if dark else '#142d48'));font=p.font();font.setPointSize(11);font.setBold(True);p.setFont(font)
        p.drawText(18,31,self.heading)
        items=self.values[:6]
        if not items or all(sum(max(0,float(x)) for x in item[1:])<=0 for item in items):
            p.setPen(QColor('#8192a5'));font.setBold(False);font.setPointSize(10);p.setFont(font)
            p.drawText(r.adjusted(15,40,-15,-10),Qt.AlignmentFlag.AlignCenter,'Bu dönem için veri yok')
            return
        if self.kind=='trend':
            self._trend(p,items)
        else:
            self._donut(p,items)
    def _donut(self,p,items):
        total=sum(max(0,float(item[1])) for item in items)
        if not total:return
        diameter=min(max(80,self.height()-95),max(100,int(self.width()*.42)))
        x=20;y=(self.height()+32-diameter)/2
        arc=QRectF(x,y,diameter,diameter)
        start=90*16
        pen=QPen();pen.setWidth(max(13,int(diameter*.16)));pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        inner=arc.adjusted(pen.width()/2,pen.width()/2,-pen.width()/2,-pen.width()/2)
        for i,item in enumerate(items):
            v=max(0,float(item[1]));span=round(-360*16*v/total)
            pen.setColor(QColor(self.PALETTE[i%len(self.PALETTE)]));p.setPen(pen);p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(inner,start,span);start+=span
        p.setPen(QColor('#edf8ff' if self.property('darkTheme') else '#183651'));font=p.font();font.setPointSize(10);font.setBold(True);p.setFont(font)
        p.drawText(arc,Qt.AlignmentFlag.AlignCenter,f'{total/100:,.0f} ₺')
        font.setPointSize(9);font.setBold(False);p.setFont(font)
        lx=int(diameter+36);available=max(55,self.width()-lx-13)
        for i,item in enumerate(items[:6]):
            yy=55+i*25
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(self.PALETTE[i%len(self.PALETTE)]));p.drawEllipse(lx,yy,9,9)
            p.setPen(QColor('#c4dcec' if self.property('darkTheme') else '#435a6b'))
            label=str(item[0]);label=label[:max(4,available//9)]
            p.drawText(lx+16,yy+9,label)
    def _trend(self,p,items):
        plot=QRectF(40,58,max(75,self.width()-58),max(70,self.height()-90))
        maxval=max(float(x) for it in items for x in it[1:]) or 1
        p.setPen(QPen(QColor('#e7eef5'),1))
        for i in range(4):
            y=plot.bottom()-i*plot.height()/3;p.drawLine(int(plot.left()),int(y),int(plot.right()),int(y))
        n=len(items);group_w=plot.width()/max(1,n);bar=max(5,min(22,group_w*.26))
        for i,item in enumerate(items):
            x=plot.left()+i*group_w+group_w*.22
            for j,v in enumerate(item[1:3]):
                h=max(0,float(v))/maxval*(plot.height()-12)
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#22bea9' if j==0 else '#ffac61'))
                p.drawRoundedRect(QRectF(x+j*(bar+3),plot.bottom()-h,bar,h),3,3)
            p.setPen(QColor('#607488'));font=p.font();font.setPointSize(8);p.setFont(font)
            p.drawText(QRectF(plot.left()+i*group_w,plot.bottom()+5,group_w,20),Qt.AlignmentFlag.AlignCenter,str(item[0])[-5:])

class InlineDialog(QDialog):
    """Compatibility form: keeps existing handlers while showing forms inside main stack."""
    def exec(self):
        host = self.parent()
        if host is None or not hasattr(host, 'stack'):
            return super().exec()
        host._decorate_bank_widgets(self)
        stack = host.stack
        previous = stack.currentWidget()
        # Use a QWidget presentation, not a separate top-level/modal window.
        self.setWindowFlags(Qt.WindowType.Widget)
        stack.addWidget(self)
        stack.setCurrentWidget(self)
        host.heading.setText(self.windowTitle() or 'İşlem Formu')
        self.show()
        loop = QEventLoop()
        result = {'code': QDialog.DialogCode.Rejected}
        def accepted():
            result['code'] = QDialog.DialogCode.Accepted
            loop.quit()
        def rejected():
            loop.quit()
        self.accepted.connect(accepted)
        self.rejected.connect(rejected)
        try:
            loop.exec()
        finally:
            self.accepted.disconnect(accepted)
            self.rejected.disconnect(rejected)
            stack.setCurrentWidget(previous)
            stack.removeWidget(self)
            self.setParent(None)
            self.deleteLater()
            host.heading.setText(host.page_titles[stack.currentIndex()])
        return result['code']


def init_account_bank_catalog(db):
    """Backward-compatible, non-destructive extension: bank label for each account."""
    with db:
        db.execute("""CREATE TABLE IF NOT EXISTS account_bank_details (
            account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE RESTRICT,
            bank_name TEXT NOT NULL CHECK(length(bank_name) BETWEEN 1 AND 100)
        )""")


def list_bank_names():
    """Curated offline starters, not an authoritative list of all licensed banks."""
    from card_catalog import SEED
    additional = {'Türkiye Cumhuriyeti Ziraat Bankası', 'Türkiye Vakıflar Bankası',
                  'Türkiye Halk Bankası', 'Alternatif Bank', 'Aktif Bank',
                  'ICBC Turkey', 'Türkiye Emlak Katılım',
                  'Vakıf Katılım', 'Dünya Katılım Bankası'}
    return sorted(set(SEED) | additional, key=str.casefold)


class BankSelectionCombo(QComboBox):
    """Compact searchable bank selection with proportional, padded logo slots."""
    ROW_HEIGHT = 32
    VISIBLE_ROWS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('bankSelection')
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMinimumHeight(36)
        self.setMaximumWidth(420)
        # Narrow icon region prevents wide bank-wordmarks from dominating the list.
        self.setIconSize(QSize(110, 24))
        self.setMaxVisibleItems(self.VISIBLE_ROWS)
        view = QListView(self)
        view.setUniformItemSizes(True)
        view.setSpacing(0)
        view.setIconSize(QSize(110, 24))
        view.setStyleSheet("""QListView {padding: 3px 5px;outline:0;}
            QListView::item { min-height: 32px; padding: 0px 6px; }
            QListView::item:selected {background:#d6f3f2;color:#0e344d;border-radius:5px;}""")
        self.setView(view)
        # A QCompleter supplies contains-search without expanding all banks on screen.
        completer = QCompleter(self.model(), self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setMaxVisibleItems(self.VISIBLE_ROWS)
        completer.popup().setIconSize(QSize(110, 24))
        completer.popup().setStyleSheet(view.styleSheet())
        self.setCompleter(completer)
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched == self.lineEdit() and event.type() == QEvent.Type.MouseButtonRelease:
            if not self.view().isVisible():
                self.showPopup()
        return super().eventFilter(watched, event)

    def showPopup(self):
        # Apply after population: keeps the menu short, even with many banks.
        self.setMaxVisibleItems(self.VISIBLE_ROWS)
        self.view().setIconSize(QSize(110, 24))
        self.view().setFixedHeight(self.ROW_HEIGHT * self.VISIBLE_ROWS + 8)
        self.view().setMinimumWidth(0)
        self.view().setMaximumWidth(max(250, self.width()))
        super().showPopup()


class AddAccountDialog(InlineDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Yeni hesap')
        layout = QFormLayout(self)
        self.kind = QComboBox()
        self.kind.setMinimumHeight(45)
        self.kind.setMaxVisibleItems(7)
        self.kind.addItem('Banka hesabı', 'bank')
        self.kind.addItem('Nakit / cüzdan', 'cash')
        self.bank = BankSelectionCombo()

        for bank_name in list_bank_names():
            self.bank.addItem(self._logo_icon(bank_name), bank_name)

        self.bank.setCurrentIndex(-1)
        self.bank.setPlaceholderText('Banka seçin veya adını yazın…')
        self.bank.setToolTip('Bu katalog başlangıç listesidir; eksik banka adını yazabilirsiniz.')
        self.name = QLineEdit()
        self.name.setPlaceholderText('Örneğin: Maaş hesabım')
        self.balance = QDoubleSpinBox()
        self.balance.setRange(-100000000, 100000000)
        self.balance.setDecimals(2)
        self.balance.setSuffix(' ₺')
        layout.addRow('Hesap türü', self.kind)
        layout.addRow('Banka', self.bank)
        layout.addRow('Hesap adı', self.name)
        layout.addRow('Açılış bakiyesi', self.balance)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.bank.currentTextChanged.connect(self._suggest_name)
        self._kind_changed()
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(self.accept)
        controls.rejected.connect(self.reject)
        layout.addRow(controls)

    @staticmethod
    def _logo_icon(bank_name):
        return menu_icon(logo_path(bank_name))

    def _kind_changed(self, *_):
        self.bank.setEnabled(self.kind.currentData() == 'bank')
        if self.kind.currentData() == 'cash' and not self.name.text().strip():
            self.name.setPlaceholderText('Örneğin: Cüzdanım')

    def _suggest_name(self, text):
        if self.kind.currentData() == 'bank' and not self.name.text().strip():
            self.name.setPlaceholderText(f'{text} - Vadesiz Hesap' if text.strip() else 'Örneğin: Maaş hesabım')


class AddTransactionDialog(InlineDialog):
    def __init__(self, accounts, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Yeni gelir / gider')
        layout = QFormLayout(self)
        self.kind = QComboBox()
        self.kind.addItem('Gider', 'expense')
        self.kind.addItem('Gelir', 'income')
        self.account = QComboBox()
        for a in accounts:
            self.account.addItem(a[1], a[0])
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(['Market', 'Fatura', 'Ulaşım', 'Kira', 'Maaş', 'Ek gelir', 'Diğer'])
        self.description = QLineEdit()
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0.01, 100000000)
        self.amount.setDecimals(2)
        self.amount.setValue(100.00)
        self.amount.setSuffix(' ₺')
        for label, widget in [('İşlem', self.kind), ('Hesap', self.account), ('Kategori', self.category),
                              ('Açıklama', self.description), ('Tutar', self.amount)]:
            layout.addRow(label, widget)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(self.accept)
        controls.rejected.connect(self.reject)
        layout.addRow(controls)


def from_spin(spin):
    return int((Decimal(str(spin.value())) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = open_db()
        migrate_record_state(self.db)
        migrate_recurring(self.db)
        migrate_products(self.db)
        self._row_ids={'account':[], 'card':[], 'kmh':[]}
        self.dark = False
        self.setWindowTitle('ParaNoya · Paranın peşini bırakma! · v1.2.5.6')
        self.setWindowIcon(QIcon(str(Path(__file__).parent/'assets'/'paranoya_mascot.png')))
        self.resize(1440, 900)
        self.setMinimumSize(920, 600)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(12, 12, 14, 12)
        outer.setSpacing(14)
        sidebar=QWidget();sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(238)
        left=QVBoxLayout(sidebar)
        left.setContentsMargins(12,12,12,12)
        left.setSpacing(7)
        brand_panel=QWidget();brand_panel.setObjectName('brandPanel')
        brand_row=QHBoxLayout(brand_panel);brand_row.setContentsMargins(8,9,8,9);brand_row.setSpacing(8)
        brand_panel.setMinimumHeight(80);brand_panel.setMaximumHeight(94)
        mascot=QLabel();mascot.setObjectName('mascotAvatar');mascot.setFixedSize(60,60)
        mascot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mascot.setPixmap(circular_mascot(Path(__file__).parent/'assets'/'paranoya_mascot.png'))
        brand_row.addWidget(mascot)
        brand_text=QVBoxLayout();brand_text.setSpacing(4)
        brand=QLabel('<span style="color:#ffffff">Para</span><span style="color:#2ad6ca">Noya</span>');brand.setTextFormat(Qt.TextFormat.RichText);brand.setObjectName('brand')
        brand.setMinimumWidth(124)
        brand_text.addWidget(brand)
        slogan=QLabel('Paranın peşini bırakma!');slogan.setObjectName('slogan');brand_text.addWidget(slogan)
        brand_row.addLayout(brand_text);left.addWidget(brand_panel)
        area_label=QLabel('ÇALIŞMA ALANI');area_label.setObjectName('sidebarCaption');left.addWidget(area_label)
        self.profile = QComboBox()
        for pid, name in get_profiles(self.db):
            self.profile.addItem(name, pid)
        self.profile.currentIndexChanged.connect(self.refresh)
        left.addWidget(self.profile)
        menu_scroll=QScrollArea()
        menu_scroll.setObjectName('sidebarMenuScroll')
        menu_scroll.setWidgetResizable(True)
        menu_scroll.setFrameShape(QFrame.Shape.NoFrame)
        menu_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        menu_widget=QWidget();menu_widget.setObjectName('sidebarMenuContent')
        menu_layout=QVBoxLayout(menu_widget)
        menu_layout.setContentsMargins(0,7,0,7)
        menu_layout.setSpacing(5)
        menu_scroll.setWidget(menu_widget)
        left.addWidget(menu_scroll, 1)
        self.stack = QStackedWidget()
        self.page_titles = ['Genel Bakış', 'Hesaplarım', 'Gelir ve Giderler', 'Aile Paylaşımı', 'Hesaplar Arası Transfer', 'Kredi Kartları ve Taksitler', 'Ortak Gider Geçmişi', 'Ek Hesap / KMH', 'Aylık Ödemeler', 'Akıllı Belge Merkezi', 'Faturalar ve Abonelikler', 'Ürünler ve Garantiler']
        self.nav_buttons = []
        # Navigation order is independent from the QStackedWidget page indices.
        nav_groups = [
            ('GENEL', [(0, '⌂  Genel Bakış')]),
            ('GÜNLÜK FİNANS', [(1, '▣  Banka Hesapları'), (2, '◉  Gelir / Gider'), (4, '⇄  Transferler')]),
            ('BORÇLAR VE ÖDEMELER', [(5, '▤  Kredi Kartları'), (7, '₺  Ek Hesap / KMH'), (8, '▦  Aylık Ödemeler'), (10, '↻  Faturalar / Abonelikler')]),
            ('AİLE', [(3, '♧  Aile Paylaşımı'), (6, '▥  Ortak Gider Geçmişi')]),
            ('BELGELER VE DİĞER', [(9, '▧  Akıllı Belge Merkezi'), (11, '▣  Ürünler / Garantiler')]),
        ]
        self.nav_map = {}
        for group, entries in nav_groups:
            heading = QLabel(group)
            heading.setObjectName('navGroupHeading')
            menu_layout.addWidget(heading)
            for page_index, label in entries:
                btn = QPushButton(label)
                btn.setProperty('nav', True)
                btn.clicked.connect(lambda _=False, i=page_index: self.select_page(i))
                self.nav_map[page_index] = btn
                menu_layout.addWidget(btn)
        for label in ['▥  Raporlar  ·  Yakında']:
            btn = QPushButton(label)
            btn.setEnabled(False)
            menu_layout.addWidget(btn)
        menu_layout.addStretch()
        # Logo indirme teknik bir işlemdir: kalıcı sol menü düğmesi yoktur.
        self.logo_status = QLabel('')
        self.logo_status.setObjectName('logoDownloadStatus')
        self.logo_status.setWordWrap(True)
        self.logo_status.hide()
        left.addWidget(self.logo_status)
        from in_app_updates import UpdateCheckController
        self.update_button=QPushButton('↻  Güncellemeleri denetle')
        self.update_button.setObjectName('sidebarUpdate')
        self.update_button.setToolTip('İmzalı sürümü denetle; kurulumdan önce onayınız istenir')
        self.update_controller=UpdateCheckController(self,self.update_button)
        self.update_button.clicked.connect(self.update_controller.start)
        left.addWidget(self.update_button)
        theme_btn = QPushButton('☼ / ☾  Temayı değiştir')
        theme_btn.clicked.connect(self.toggle_theme)
        left.addWidget(theme_btn)
        outer.addWidget(sidebar)
        content = QVBoxLayout()
        self.heading = QLabel()
        self.heading.setObjectName('heading')
        topbar=QHBoxLayout();topbar.setSpacing(12)
        self.search_box=QLineEdit();self.search_box.setObjectName('globalSearch')
        self.search_box.setPlaceholderText('⌕   İşlem, hesap veya kategori ara...')
        self.search_box.returnPressed.connect(self.global_search)
        topbar.addWidget(self.search_box,2)
        self.profile_badge=QLabel('◉  Kişisel / Aile');self.profile_badge.setObjectName('profileBadge')
        topbar.addStretch();topbar.addWidget(self.profile_badge)
        content.addLayout(topbar)
        content.addWidget(self.heading)
        self.notice = QLabel('Belgeler onayınızla kaydedilir  •  Profil seçimi güvenli oturum değildir.')
        self.notice.setWordWrap(True)
        content.addWidget(self.notice)
        self.dashboard=QWidget()
        self.dashboard.setMinimumSize(1100,650)
        dash=QVBoxLayout(self.dashboard);dash.setSpacing(14)
        overview=QGridLayout();overview.setSpacing(10)
        self.balance_value=self.make_card(overview,0,'◈  Hesap Bakiyesi')
        self.debt_value=self.make_card(overview,1,'▣  Toplam Kart Borcu')
        self.income_value=self.make_card(overview,2,'↗  Toplam Gelir')
        self.expense_value=self.make_card(overview,3,'↘  Toplam Gider')
        self.remaining_value=self.make_card(overview,4,'◎  Gelir - Gider Farkı')
        dash.addLayout(overview)
        middle=QHBoxLayout();middle.setSpacing(12)
        from PySide6.QtWidgets import QSizePolicy
        self.category_chart=FinanceBars('Giderlerin Kategori Dağılımı')
        self.trend_chart=FinanceBars('Aylık Gelir - Gider Trendi','trend')
        self.asset_chart=FinanceBars('Pozitif Hesap Bakiyeleri')
        middle.addWidget(self.category_chart,2);middle.addWidget(self.trend_chart,2);middle.addWidget(self.asset_chart,2)
        dash.addLayout(middle,2)
        bottom=QHBoxLayout();bottom.setSpacing(12)
        recent_box=QGroupBox('Son İşlemler');recent_layout=QVBoxLayout(recent_box)
        self.recent=self.make_table(['Tarih','Tür','Hesap','Kategori','Tutar']);recent_layout.addWidget(self.recent)
        bottom.addWidget(recent_box,3)
        due_box=QGroupBox('Yaklaşan Ödemeler');due_layout=QVBoxLayout(due_box)
        self.dashboard_due=self.make_table(['Vade','Kart / Hesap','Tutar'])
        due_layout.addWidget(self.dashboard_due);bottom.addWidget(due_box,2)
        quick_box=QGroupBox('Hızlı İşlemler');quick_box.setObjectName('quickActions');quick=QVBoxLayout(quick_box)
        for lbl,cb in [('＋  İşlem Ekle',self.create_transaction),('⇄  Transfer',self.create_transfer),('▧  Ekstre Yükle',self.import_document),('▣  Kart Ekle',self.new_card)]:
            b=QPushButton(lbl);b.clicked.connect(cb);quick.addWidget(b)
        quick.addStretch();bottom.addWidget(quick_box,1)
        dash.addLayout(bottom,3)
        dashboard_scroll=QScrollArea()
        dashboard_scroll.setWidgetResizable(True)
        dashboard_scroll.setFrameShape(QFrame.Shape.NoFrame)
        dashboard_scroll.setWidget(self.dashboard)
        self.stack.addWidget(dashboard_scroll)
        accounts_page = QWidget()
        ac_layout = QVBoxLayout(accounts_page)
        new_acc = QPushButton('+ Yeni hesap')
        new_acc.clicked.connect(self.create_account)
        ac_layout.addWidget(new_acc, alignment=Qt.AlignmentFlag.AlignLeft)
        self.acc_table = self.make_table(['Hesap', 'Tür', 'Bakiye'])
        self._add_actions(ac_layout, self.acc_table, 'account')
        account_metrics=QHBoxLayout()
        self.acc_total_count=QLabel('0')
        self.acc_total_balance=QLabel('₺0,00')
        self.acc_positive_balance=QLabel('₺0,00')
        for caption, value in [('HESAP SAYISI',self.acc_total_count), ('TOPLAM HESAP BAKİYESİ',self.acc_total_balance), ('POZİTİF BAKİYELER',self.acc_positive_balance)]:
            tile=QFrame();tile.setObjectName('cardMetric');v=QVBoxLayout(tile)
            title=QLabel(caption);title.setObjectName('metricCaption');v.addWidget(title)
            value.setObjectName('metricNumber');v.addWidget(value)
            account_metrics.addWidget(tile)
        ac_layout.insertLayout(1,account_metrics)
        ac_layout.addWidget(self.acc_table)
        self.account_details=QFrame();self.account_details.setObjectName('cardDetails')
        ad=QVBoxLayout(self.account_details)
        self.account_detail_heading=QLabel('Bir hesap seçerek ayrıntılarını görüntüleyin')
        self.account_detail_heading.setObjectName('cardDetailHeading')
        self.account_detail_body=QLabel('Hesap türü, bakiye ve bağlı KMH bilgileri burada görünür.')
        self.account_detail_body.setWordWrap(True)
        self.account_logo=QLabel()
        self.account_logo.setFixedHeight(34)
        self.account_logo.hide()
        logo_row=QHBoxLayout()
        logo_row.addWidget(self.account_logo)
        logo_row.addWidget(self.account_detail_heading, 1)
        ad.addLayout(logo_row)
        ad.addWidget(self.account_detail_body)
        ac_layout.addWidget(self.account_details)
        self.acc_table.itemSelectionChanged.connect(self.update_account_details)
        self.stack.addWidget(accounts_page)
        transactions_page = QWidget()
        tx_layout = QVBoxLayout(transactions_page)
        new_tx = QPushButton('+ Yeni gelir / gider')
        new_tx.clicked.connect(self.create_transaction)
        tx_layout.addWidget(new_tx, alignment=Qt.AlignmentFlag.AlignLeft)
        self.tx_table = self.make_table(['Tarih', 'Tür', 'Hesap', 'Kategori', 'Açıklama', 'Tutar'])
        tx_layout.addWidget(self.tx_table)
        self.stack.addWidget(transactions_page)
        family_page = QWidget()
        fam = QVBoxLayout(family_page)
        add_mem = QPushButton('+ Aile üyesi ekle')
        add_mem.clicked.connect(self.create_member)
        fam.addWidget(add_mem, alignment=Qt.AlignmentFlag.AlignLeft)
        shared_btn = QPushButton('+ Ortak gider ekle ve paylaştır')
        shared_btn.clicked.connect(self.create_shared_expense)
        fam.addWidget(shared_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        fam.addWidget(QLabel('Aile üyelerinin paylarına düşen toplam ortak giderler'))
        self.members_table = self.make_table(['Aile üyesi', 'Gider payı'])
        fam.addWidget(self.members_table)
        self.stack.addWidget(family_page)
        transfer_page = QWidget()
        tl = QVBoxLayout(transfer_page)
        transfer_btn = QPushButton('+ Yeni transfer')
        transfer_btn.clicked.connect(self.create_transfer)
        tl.addWidget(transfer_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.transfers_table = self.make_table(['Tarih', 'Gönderen', 'Alıcı', 'Tutar', 'Açıklama'])
        tl.addWidget(self.transfers_table)
        self.stack.addWidget(transfer_page)
        cardpage=QWidget(); cl=QVBoxLayout(cardpage)
        for label,callback in [('+ Kart ekle',self.new_card),('+ Taksitli alışveriş',self.new_purchase),('+ Kart borcu öde',self.new_card_payment)]:
            b=QPushButton(label);b.clicked.connect(callback);cl.addWidget(b,alignment=Qt.AlignmentFlag.AlignLeft)
        card_metrics=QHBoxLayout();card_metrics.setSpacing(12)
        self.card_total_label=QLabel('₺0,00');self.card_limit_label=QLabel('₺0,00');self.card_available_label=QLabel('₺0,00')
        for title,widget in [('TOPLAM KART BORCU',self.card_total_label),('TOPLAM KART LİMİTİ',self.card_limit_label),('TAHMİNİ KULLANILABİLİR',self.card_available_label)]:
            tile=QFrame();tile.setObjectName('cardMetric');v=QVBoxLayout(tile)
            cap=QLabel(title);cap.setObjectName('metricCaption');v.addWidget(cap)
            widget.setObjectName('metricNumber');v.addWidget(widget)
            card_metrics.addWidget(tile)
        cl.addLayout(card_metrics)
        cl.addWidget(QLabel('Kartlarım · İşlem yapmak için bir kart seçin'))
        self.card_table=self.make_table(['Kart','Kesim','Ödeme günü','Limit','Kalan borç'])
        self._add_actions(cl,self.card_table,'card');cl.addWidget(self.card_table)
        self.card_details=QFrame();self.card_details.setObjectName('cardDetails');detail_layout=QVBoxLayout(self.card_details)
        self.card_detail_heading=QLabel('Kart seçildiğinde ayrıntıları burada görünecek')
        self.card_detail_heading.setObjectName('cardDetailHeading')
        self.card_detail_body=QLabel('Banka, kart modeli, ödeme ağı, limit ve borç bilgileri')
        self.card_detail_body.setWordWrap(True)
        self.card_logo=QLabel()
        self.card_logo.setFixedHeight(34)
        self.card_logo.hide()
        logo_row=QHBoxLayout()
        logo_row.addWidget(self.card_logo)
        logo_row.addWidget(self.card_detail_heading, 1)
        detail_layout.addLayout(logo_row)
        detail_layout.addWidget(self.card_detail_body)
        cl.addWidget(self.card_details)
        cl.addWidget(QLabel('Yaklaşan taksitler (tahmini tarihler)'))
        self.due_table=self.make_table(['Kart','Vade','Ödenmemiş tutar','Kategori','Açıklama']);cl.addWidget(self.due_table)
        self.stack.addWidget(cardpage)
        historypage=QWidget(); hl=QVBoxLayout(historypage)
        correct=QPushButton('Seçili giderin paylarını düzelt');correct.clicked.connect(self.correct_split)
        hl.addWidget(correct,alignment=Qt.AlignmentFlag.AlignLeft)
        self.shared_table=self.make_table(['ID','Tarih','Ödeyen hesap','Kategori','Gider','Üye payları'])
        hl.addWidget(self.shared_table);self.stack.addWidget(historypage)
        kmhpage=QWidget(); kl=QVBoxLayout(kmhpage)
        for label,fn in [('+ Banka hesabına ek limit',self.new_overdraft),('+ KMH kullan / kapat',self.kmh_draw_repay),('+ Taksitli KMH borcu',self.new_kmh_loan)]:
            b=QPushButton(label);b.clicked.connect(fn);kl.addWidget(b,alignment=Qt.AlignmentFlag.AlignLeft)
        kmh_metrics=QHBoxLayout()
        self.kmh_limit_total=QLabel('₺0,00')
        self.kmh_used_total=QLabel('₺0,00')
        self.kmh_available_total=QLabel('₺0,00')
        for caption, value in [('TOPLAM KMH LİMİTİ',self.kmh_limit_total),('KULLANILAN KMH',self.kmh_used_total),('KALAN KMH LİMİTİ',self.kmh_available_total)]:
            tile=QFrame();tile.setObjectName('cardMetric');v=QVBoxLayout(tile)
            label=QLabel(caption);label.setObjectName('metricCaption');v.addWidget(label)
            value.setObjectName('metricNumber');v.addWidget(value)
            kmh_metrics.addWidget(tile)
        kl.addLayout(kmh_metrics)
        self.kmh_table=self.make_table(['Banka hesabı','KMH limiti','Kullanılan','Kalan limit']);self._add_actions(kl,self.kmh_table,'kmh');kl.addWidget(self.kmh_table)
        self.kmh_details=QFrame();self.kmh_details.setObjectName('cardDetails')
        kd=QVBoxLayout(self.kmh_details)
        self.kmh_detail_heading=QLabel('Bir KMH hesabı seçin')
        self.kmh_detail_heading.setObjectName('cardDetailHeading')
        self.kmh_detail_body=QLabel('Kullanım, kalan limit ve bağlı taksitli borçların özeti burada görünür.')
        self.kmh_detail_body.setWordWrap(True)
        self.kmh_logo=QLabel()
        self.kmh_logo.setFixedHeight(34)
        self.kmh_logo.hide()
        logo_row=QHBoxLayout()
        logo_row.addWidget(self.kmh_logo)
        logo_row.addWidget(self.kmh_detail_heading, 1)
        kd.addLayout(logo_row)
        kd.addWidget(self.kmh_detail_body)
        kl.addWidget(self.kmh_details)
        self.kmh_table.itemSelectionChanged.connect(self.update_kmh_details)
        kl.addWidget(QLabel('Taksitli KMH planları ayrı borç olarak izlenir.'))
        self.stack.addWidget(kmhpage)
        calpage=QWidget(); cal=QVBoxLayout(calpage)
        b=QPushButton('Seçili KMH taksidini öde');b.clicked.connect(self.kmh_pay);cal.addWidget(b,alignment=Qt.AlignmentFlag.AlignLeft)
        calendar_metrics=QHBoxLayout()
        self.calendar_month_label=QLabel('₺0,00')
        self.calendar_overdue_label=QLabel('₺0,00')
        self.calendar_total_label=QLabel('₺0,00')
        for caption, value in [('BU AY ÖDENECEK',self.calendar_month_label),('GECİKEN',self.calendar_overdue_label),('TOPLAM BEKLEYEN',self.calendar_total_label)]:
            tile=QFrame();tile.setObjectName('cardMetric');v=QVBoxLayout(tile)
            label=QLabel(caption);label.setObjectName('metricCaption');v.addWidget(label)
            value.setObjectName('metricNumber');v.addWidget(value);calendar_metrics.addWidget(tile)
        cal.addLayout(calendar_metrics)
        filter_bar=QHBoxLayout();filter_bar.addWidget(QLabel('Takvim filtresi:'))
        self.calendar_filter=QComboBox()
        for label, code in [('Tüm bekleyenler','all'),('Bu ay','this_month'),('Gecikenler','overdue'),('Gelecek ödemeler','future')]:
            self.calendar_filter.addItem(label,code)
        self.calendar_filter.currentIndexChanged.connect(self.refresh_calendar)
        filter_bar.addWidget(self.calendar_filter);filter_bar.addStretch()
        cal.addLayout(filter_bar)
        self.calendar_table=self.make_table(['ID','Banka','Vade','Ödenecek','Durum','Açıklama']);cal.addWidget(self.calendar_table)
        cal.addWidget(QLabel('Fatura / abonelik yenilemeleri (ödeme onaylanmadan gider değildir)'))
        self.calendar_recurring=self.make_table(['Ad','Tür','Vade','Tutar'])
        cal.addWidget(self.calendar_recurring)
        self.stack.addWidget(calpage)
        documents_page=QWidget()
        dv=QVBoxLayout(documents_page)
        dv.addWidget(QLabel('Bordro, fatura ve ekstre yerel okunur; bilgileri kontrol edip onaylayınca finans kaydı oluşur.'))
        upload=QPushButton('+ Belge yükle (PDF, CSV, Excel, TXT)')
        upload.clicked.connect(self.import_document)
        dv.addWidget(upload,alignment=Qt.AlignmentFlag.AlignLeft)
        self.doc_table=self.make_table(['ID','Dosya','Tür','Durum','Tarih'])
        dv.addWidget(self.doc_table)
        preview_button=QPushButton('Seçili belgedeki öneri satırlarını göster')
        preview_button.clicked.connect(self.preview_document_rows)
        dv.addWidget(preview_button,alignment=Qt.AlignmentFlag.AlignLeft)
        self.doc_preview=self.make_table(['Satır','Tarih','Açıklama / Taksit','Tutar','Durum'])
        dv.addWidget(self.doc_preview)
        dv.addWidget(QLabel('Önizleme finans kaydı oluşturmaz. Tüm satırlar bankanın belgesiyle karşılaştırılmalıdır.'))
        salary=QPushButton('Seçili belgeden gelir / gider oluştur')
        salary.clicked.connect(self.post_document_entry)
        dv.addWidget(salary,alignment=Qt.AlignmentFlag.AlignLeft)
        self.stack.addWidget(documents_page)
        # Düzenli fatura ve abonelik modülü: tüm seçimler içerik alanındadır.
        recurring_page=QWidget(); recurring_layout=QVBoxLayout(recurring_page)
        recurring_layout.addWidget(QLabel('Faturalar ve Abonelikler · Ödemeler onaylanınca bir kez gider kaydedilir'))
        entry=QGroupBox('Yeni düzenli ödeme'); entry_form=QFormLayout(entry)
        self.rec_name=QLineEdit();self.rec_name.setPlaceholderText('İnternet, elektrik, yazılım aboneliği...')
        self.rec_kind=QComboBox();self.rec_kind.addItem('Fatura','bill');self.rec_kind.addItem('Abonelik','subscription')
        self.rec_category=QLineEdit('Faturalar')
        self.rec_amount=QDoubleSpinBox();self.rec_amount.setRange(.01,99999999);self.rec_amount.setDecimals(2);self.rec_amount.setSuffix(' TL')
        self.rec_freq=QComboBox()
        for label,value in [('Aylık','monthly'),('3 ayda bir','quarterly'),('Yıllık','yearly')]:self.rec_freq.addItem(label,value)
        self.rec_due=QDateEdit();self.rec_due.setCalendarPopup(True);self.rec_due.setDate(QDate.currentDate());self.rec_due.setDisplayFormat('dd.MM.yyyy')
        for label,widget in [('Ad',self.rec_name),('Tür',self.rec_kind),('Kategori',self.rec_category),('Tutar',self.rec_amount),('Yenileme sıklığı',self.rec_freq),('İlk vade',self.rec_due)]:entry_form.addRow(label,widget)
        save_rec=QPushButton('＋  Düzenli ödeme ekle');save_rec.clicked.connect(self.save_recurring)
        entry_form.addRow(save_rec);recurring_layout.addWidget(entry)
        recurring_layout.addWidget(QLabel('Gelecek ödemeler · Seçip hesap üzerinden ödeme yapabilirsiniz'))
        self.rec_table=self.make_table(['ID','Ad','Tür','Vade','Tutar','Kategori']);recurring_layout.addWidget(self.rec_table)
        rec_buttons=QHBoxLayout();rec_pay=QPushButton('Seçili dönemi öde');rec_pay.clicked.connect(self.pay_recurring)
        rec_pause=QPushButton('Seçili aboneliği / faturayı durdur');rec_pause.clicked.connect(self.pause_recurring)
        rec_buttons.addWidget(rec_pay);rec_buttons.addWidget(rec_pause);rec_buttons.addStretch();recurring_layout.addLayout(rec_buttons)
        self.stack.addWidget(recurring_page)
        products_page=QWidget(); pv=QVBoxLayout(products_page)
        pv.addWidget(QLabel('Ürünler, garantiler ve servis kayıtları · Finans hareketi otomatik oluşturulmaz.'))
        tools=QHBoxLayout()
        for title,callback in [('＋ Ürün ekle',self.new_product),('Arşivle',lambda:self.product_state('archived')),('Geri yükle',lambda:self.product_state('active')),('＋ Servis kaydı',self.new_service),('＋ Belge bağla',self.new_product_document),('Belgeleri görüntüle',self.show_product_documents)]:
            btn=QPushButton(title);btn.clicked.connect(callback);tools.addWidget(btn)
        tools.addStretch();pv.addLayout(tools)
        self.product_show_archived=QCheckBox('Arşivlenenleri de göster')
        self.product_show_archived.stateChanged.connect(self.refresh_products)
        pv.addWidget(self.product_show_archived)
        self.products_table=self.make_table(['Ad','Marka','Model','Satın alma','Fiyat','Garanti bitişi','Durum'])
        pv.addWidget(self.products_table)
        self.products_note=QLabel('');pv.addWidget(self.products_note)
        self.stack.addWidget(products_page)

        self.dashboard_info=QLabel('');self.dashboard_info.setObjectName('dashboardFoot');dash.addWidget(self.dashboard_info)
        content.addWidget(self.stack, 1)
        outer.addLayout(content, 1)
        self.select_page(0)
        self.apply_theme()
        # Arayüz hazır olduğunda eksik logoları asenkron indir.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(250, self.download_bank_logos)

    def global_search(self):
        term=self.search_box.text().strip()
        if not term:return
        self.select_page(2)
        for r in range(self.tx_table.rowCount()):
            hit=any(term.casefold() in (self.tx_table.item(r,c).text() if self.tx_table.item(r,c) else '').casefold() for c in range(self.tx_table.columnCount()))
            self.tx_table.setRowHidden(r,not hit)

    def make_card(self, grid, col, title):
        box = QFrame()
        box.setObjectName('overviewCard')
        box.setProperty('tone', ['teal', 'rose', 'green', 'orange', 'blue'][col])
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 14, 14, 14)
        caption = QLabel(title)
        caption.setObjectName('overviewCaption')
        caption.setToolTip(title)
        layout.addWidget(caption)
        value = QLabel('0,00 ₺')
        value.setObjectName('stat')
        layout.addWidget(value)
        footnote = QLabel('Seçili çalışma alanı · tüm kayıtlar')
        footnote.setObjectName('overviewNote')
        footnote.setWordWrap(True)
        layout.addWidget(footnote)
        grid.addWidget(box, 0, col)
        return value

    def make_table(self, headings):
        table = QTableWidget(0, len(headings))
        table.setHorizontalHeaderLabels(headings)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(36)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        return table

    def _add_actions(self,layout,table,kind):
        """Context toolbar directly above its table; no secondary selection window."""
        bar=QHBoxLayout()
        label=QLabel('Bir kayıt seçin')
        bar.addWidget(label)
        buttons={}
        for caption, operation in [('Düzenle','edit'),('Sil','trash'),('Arşivle','archive'),('Geri yükle','restore')]:
            button=QPushButton(caption)
            button.setEnabled(False)
            button.clicked.connect(lambda _=False,k=kind,o=operation: self._record_action(k,o))
            bar.addWidget(button)
            buttons[operation]=button
        bar.addStretch()
        layout.addLayout(bar)
        self.__dict__.setdefault('_record_bars',{})[kind]=(table,label,buttons)
        table.itemSelectionChanged.connect(lambda k=kind:self._selection_changed(k))

    def _selection_changed(self,kind):
        table,label,buttons=self._record_bars[kind]
        row=table.currentRow()
        ids=getattr(self,'_row_ids',{}).get(kind,[])
        valid=0<=row<len(ids) and bool(table.selectedItems())
        state=get_state(self.db,kind,ids[row]) if valid else None
        label.setText(((table.item(row,0).text() if table.item(row,0) else '') + (' · '+state if state!='active' else '')) if valid else 'Bir kayıt seçin')
        for action,button in buttons.items():
            button.setEnabled(valid and (action=='restore' if state!='active' else action!='restore'))
        if kind=='card':
            self._show_selected_card(ids[row] if valid else None)
        if valid:
            buttons['restore'].setEnabled(state!='active')
            buttons['archive'].setEnabled(state=='active')
            buttons['trash'].setEnabled(state=='active')
            buttons['edit'].setEnabled(state=='active')

    def _show_selected_card(self, card_id):
        if not hasattr(self,'card_detail_heading'):
            return
        if card_id is None:
            self.card_detail_heading.setText('Kart seçildiğinde ayrıntıları burada görünecek')
            self.card_logo.hide()
            self.card_detail_body.setText('Banka, kart modeli, ödeme ağı, limit ve borç bilgileri')
            return
        row=self.db.execute('''SELECT c.name,c.statement_day,c.due_day,c.credit_limit_cents,
                l.bank,l.card_model,l.payment_network
                FROM credit_cards c LEFT JOIN card_catalog_links l ON l.card_id=c.id
                WHERE c.id=? AND c.profile_id=?''',(card_id,self.pid())).fetchone()
        if not row:
            return
        name,cut,due,lim,bank,model,network=row
        debt=next((c[-1] for c in cards(self.db,self.pid()) if c[0]==card_id),0)
        bank=bank or 'Banka belirtilmedi'
        model=model or name
        network=network or 'Belirtilmedi'
        initials=''.join(word[0].upper() for word in bank.split()[:2])
        self.card_detail_heading.setText(name)
        self._set_detail_logo(self.card_logo, bank)
        self.card_detail_body.setText(
            f'Banka: {bank}    |    Model: {model}    |    Ağ: {network}\n'
            f'Kart limiti: {money(lim)}    |    Kalan borç: {money(debt)}    |    '
            f'Tahmini boş limit: {money(max(0,lim-debt))}\n'
            f'Hesap kesim günü: {cut}    |    Son ödeme günü: {due}\n'
            'Not: Kullanılabilir limit, provizyonlar ve banka işlemlerine göre farklı olabilir.')

    def _record_action(self,kind,operation):
        table,_,_=self._record_bars[kind]
        ids=getattr(self,'_row_ids',{}).get(kind,[])
        r=table.currentRow()
        if not (0<=r<len(ids)): return
        record_id=ids[r]
        if operation=='edit':
            self._edit_record(kind,record_id)
            return
        target={'trash':'trashed','archive':'archived','restore':'active'}[operation]
        if target!='active':
            deps=dependencies(self.db,kind,record_id)
            extra=('\nBağlı kayıtlar: '+', '.join(f'{name}: {n}' for name,n in deps)) if deps else ''
            answer=QMessageBox.question(self,'Kaydı '+('arşivle' if target=='archived' else 'sil'),
                'Bu işlem finans geçmişini silmez.'+extra+'\nDevam edilsin mi?')
            if answer!=QMessageBox.StandardButton.Yes:return
        try:
            change_state(self.db,kind,record_id,target)
            self.refresh()
        except (ValueError,Exception) as exc:
            QMessageBox.warning(self,'Kayıt koruması',str(exc))

    def _edit_record(self,kind,record_id):
        # Tek, Türkçe etiketli ve tutarları TL olarak gösteren güvenli kayıt editörü.
        mapping = {
            'account': ('accounts', ['name']),
            'card': ('credit_cards', ['name', 'statement_day', 'due_day', 'credit_limit_cents']),
            'kmh': ('overdraft_accounts', ['limit_cents']),
        }
        table, cols = mapping[kind]
        existing = self.db.execute(
            'SELECT ' + ','.join(cols) + ' FROM ' + table + ' WHERE id=?', (record_id,)
        ).fetchone()
        if not existing:
            return

        titles = {'account': 'Banka / Nakit Hesabını Düzenle',
                  'card': 'Kredi Kartını Düzenle', 'kmh': 'Ek Hesap / KMH Limitini Düzenle'}
        labels = {'name': 'Hesap / Kart adı', 'statement_day': 'Hesap kesim günü',
                  'due_day': 'Son ödeme günü', 'credit_limit_cents': 'Kart limiti (TL)',
                  'limit_cents': 'KMH limiti (TL)'}
        dlg = InlineDialog(self)
        dlg.setWindowTitle(titles[kind])
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(22, 16, 22, 16)
        outer.setSpacing(14)
        intro = QLabel('Bilgileri düzenleyin. Kayıtlı işlemler ve geçmiş hareketler korunur.')
        intro.setWordWrap(True)
        outer.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        form = QFormLayout(body)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(14)
        fields = {}
        for field, value in zip(cols, existing):
            if field in ('credit_limit_cents', 'limit_cents'):
                widget = QDoubleSpinBox()
                widget.setDecimals(2)
                widget.setRange(0, 999999999999.99)
                widget.setSingleStep(100)
                widget.setSuffix(' ₺')
                widget.setValue(int(value) / 100)
            elif field in ('statement_day', 'due_day'):
                widget = QSpinBox()
                widget.setRange(1, 31)
                widget.setSuffix('. gün')
                widget.setValue(int(value))
            else:
                widget = QLineEdit(str(value))
                widget.setMaxLength(100)
                widget.setPlaceholderText('Ad girin')
            widget.setMinimumHeight(38)
            form.addRow(labels.get(field, field), widget)
            fields[field] = widget
        if kind == 'card':
            note = QLabel('Ödeme günü bankanızın ekstresinden kontrol edilmelidir. Kesim gününü değiştirmek mevcut ödeme planlarını otomatik değiştirmez.')
            note.setWordWrap(True)
            form.addRow('', note)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton('İptal')
        save = QPushButton('Değişiklikleri Kaydet')
        cancel.setMinimumHeight(39)
        save.setMinimumHeight(39)
        cancel.clicked.connect(dlg.reject)
        save.clicked.connect(dlg.accept)
        footer.addWidget(cancel)
        footer.addWidget(save)
        outer.addLayout(footer)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            values = []
            for col in cols:
                w = fields[col]
                if col.endswith('_cents'):
                    values.append(int((Decimal(str(w.value())) * 100).to_integral_value(rounding=ROUND_HALF_UP)))
                elif col in ('statement_day', 'due_day'):
                    values.append(w.value())
                else:
                    values.append(w.text().strip())
            if kind == 'account' and not values[0]:
                raise ValueError('Hesap adı boş olamaz.')
            if kind == 'card' and not values[0]:
                raise ValueError('Kart adı boş olamaz.')
            if kind == 'kmh':
                current_used = self.db.execute(
                    "SELECT COALESCE(SUM(CASE WHEN kind='draw' THEN amount_cents WHEN kind='repay' THEN -amount_cents ELSE 0 END),0) FROM overdraft_events WHERE overdraft_id=?",
                    (record_id,)
                ).fetchone()[0]
                if values[0] < current_used:
                    raise ValueError('Yeni limit kullanılan KMH tutarından küçük olamaz.')
            with self.db:
                self.db.execute('UPDATE ' + table + ' SET ' + ', '.join(c + '=?' for c in cols) + ' WHERE id=?', (*values, record_id))
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, 'Düzenlenemedi', str(exc))

    def refresh_products(self,*_):
        if not hasattr(self,'products_table'):return
        rows=list_products(self.db,self.pid(),self.product_show_archived.isChecked())
        self._product_ids=[r[0] for r in rows]
        self.fill_table(self.products_table,[(r[1],r[2],r[3],r[4],money(r[5]),r[6] or 'Belirtilmedi',
                                      'Arşiv' if r[7]=='archived' else 'Aktif') for r in rows])
        self.products_note.setText(f'Kayıt: {len(rows)}  ·  Önümüzdeki 30 gün içinde biten garanti: {len(expiring(self.db,self.pid()))}')

    def _product_selected(self):
        row=self.products_table.currentRow()
        if row<0 or row>=len(getattr(self,'_product_ids',[])):
            QMessageBox.information(self,'Ürün seçimi','Önce tablodan ürün seçin.');return None
        return self._product_ids[row]

    def new_product(self):
        d,f=self._form('Yeni ürün ve garanti')
        name=QLineEdit();brand=QLineEdit();model=QLineEdit();seller=QLineEdit()
        bought=QDateEdit();bought.setCalendarPopup(True);bought.setDate(QDate.currentDate());bought.setDisplayFormat('dd.MM.yyyy')
        amount=self._amount();warranty=QDateEdit();warranty.setCalendarPopup(True)
        warranty.setDate(QDate.currentDate().addYears(2));warranty.setDisplayFormat('dd.MM.yyyy')
        has_warranty=QCheckBox('Garanti bitiş tarihi var');has_warranty.setChecked(True)
        for label,widget in [('Ürün adı',name),('Marka',brand),('Model',model),('Satıcı',seller),('Alış tarihi',bought),('Alış bedeli (TL)',amount),('Garanti bilgisi',has_warranty),('Garanti bitişi',warranty)]:f.addRow(label,widget)
        self._buttons(d,f)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try:
            create_product(self.db,self.pid(),name.text(),bought.date().toString('yyyy-MM-dd'),
                from_spin(amount),warranty.date().toString('yyyy-MM-dd') if has_warranty.isChecked() else None,
                brand=brand.text(),model=model.text(),seller=seller.text())
            self.refresh_products()
        except Exception as e:QMessageBox.warning(self,'Kaydedilemedi',str(e))

    def product_state(self,state):
        ident=self._product_selected()
        if ident is None:return
        if QMessageBox.question(self,'Kaydı güncelle','Seçili ürün '+('arşivlensin' if state=='archived' else 'geri yüklensin')+' mi?')!=QMessageBox.StandardButton.Yes:return
        try:change_product(self.db,self.pid(),ident,state=state);self.refresh_products()
        except Exception as e:QMessageBox.warning(self,'İşlem başarısız',str(e))

    def new_service(self):
        ident=self._product_selected()
        if ident is None:return
        d,f=self._form('Servis / bakım kaydı');note=QLineEdit();cost=self._amount()
        day=QDateEdit();day.setCalendarPopup(True);day.setDate(QDate.currentDate());day.setDisplayFormat('dd.MM.yyyy')
        for label,w in [('Tarih',day),('Açıklama',note),('Maliyet (TL)',cost)]:f.addRow(label,w)
        self._buttons(d,f)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try:add_service(self.db,self.pid(),ident,day.date().toString('yyyy-MM-dd'),note.text(),from_spin(cost));self.refresh_products()
        except Exception as e:QMessageBox.warning(self,'Servis kaydı',str(e))

    def new_product_document(self):
        ident=self._product_selected()
        if ident is None:return
        filename,_=QFileDialog.getOpenFileName(self,'Ürün belgesi seç','','Belgeler (*.pdf *.png *.jpg *.jpeg *.webp)')
        if not filename:return
        d,f=self._form('Belge türü')
        typ=QComboBox()
        for label,key in [('Fatura','invoice'),('Garanti belgesi','warranty'),('Kullanım kılavuzu','manual'),('Diğer','other')]:typ.addItem(label,key)
        f.addRow('Belge türü',typ)
        self._buttons(d,f)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try:
            attach_product_document(self.db,self.pid(),ident,filename,DB_DIR/'product_documents',typ.currentData())
            self.refresh_products()
            QMessageBox.information(self,'Belge kaydedildi','Belgenin kopyası uygulama veri klasörüne kaydedildi.')
        except Exception as e:QMessageBox.warning(self,'Belge eklenemedi',str(e))

    def show_product_documents(self):
        ident=self._product_selected()
        if ident is None:return
        docs=list_product_documents(self.db,self.pid(),ident)
        if not docs:
            QMessageBox.information(self,'Ürün belgeleri','Bu ürüne henüz belge bağlanmadı.');return
        d,f=self._form('Ürün belgeleri')
        choose=QComboBox()
        kinds={'invoice':'Fatura','warranty':'Garanti','manual':'Kılavuz','other':'Diğer'}
        for row in docs:choose.addItem(f'{kinds.get(row[1],row[1])} · {row[2]}',row[0])
        f.addRow('Bağlı belgeler',choose)
        self._buttons(d,f)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try:
            path=document_path(self.db,self.pid(),choose.currentData(),DB_DIR/'product_documents')
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise ValueError('Belge varsayılan uygulamada açılamadı')
        except Exception as e:QMessageBox.warning(self,'Belge açılamadı',str(e))

    def pid(self):
        return self.profile.currentData()

    def select_page(self, index):
        self.stack.setCurrentIndex(index)
        self.heading.setText(self.page_titles[index])
        self._mark_active_nav()
        self.refresh()

    def fill_table(self, table, rows):
        table.setIconSize(QSize(110, 24))
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if str(value).endswith('₺') and str(value).startswith(('-', '+')):
                    item.setForeground(QColor('#f0607c' if str(value).startswith('-') else '#009e83'))
                heading = table.horizontalHeaderItem(c).text()
                if heading in {'Hesap', 'Kart', 'Banka hesabı', 'Gönderen', 'Alıcı', 'Ödeyen hesap'}:
                    bank = self._bank_for_text(str(value))
                    if bank:
                        item.setIcon(self._bank_icon(bank))
                table.setItem(r, c, item)

    def refresh(self, *_):
        pid = self.pid()
        if pid is None:
            return
        self._bank_aliases = self._build_bank_aliases()
        income, expense, balance = summary(self.db, pid)
        self.income_value.setText(money(income))
        self.expense_value.setText(money(expense))
        self.balance_value.setText(money(balance))
        self.debt_value.setText(money(sum(c[-1] for c in cards(self.db,pid))))
        self.remaining_value.setText(money(income-expense))
        self.refresh_charts(pid)
        self.refresh_products()
        accs = accounts_with_balances(self.db, pid)
        self._row_ids['account']=[a[0] for a in accs]
        self.fill_table(self.acc_table, [(name, 'Nakit' if kind == 'cash' else 'Banka', money(bal))
                                         for _, name, kind, bal in accs])
        self.acc_total_count.setText(str(len(accs)))
        self.acc_total_balance.setText(money(sum(a[3] for a in accs)))
        self.acc_positive_balance.setText(money(sum(max(0,a[3]) for a in accs)))
        self._selection_changed('account')
        self.update_account_details()
        rows = self.db.execute('''SELECT * FROM (SELECT t.recorded_at AS happened,t.kind,a.name,t.category,t.description,t.amount_cents
            FROM transactions t JOIN accounts a ON a.id=t.account_id
            WHERE t.profile_id=?
            UNION ALL SELECT p.purchase_date,'card_expense',c.name,p.category,p.description,p.total_cents
            FROM card_purchases p JOIN credit_cards c ON c.id=p.card_id WHERE c.profile_id=?)
            ORDER BY happened DESC''', (pid,pid)).fetchall()
        shown = [(when, 'Gelir' if kind == 'income' else ('Kart gideri' if kind=='card_expense' else 'Gider'), acct, cat, note,
                  ('+' if kind == 'income' else '-') + money(amt))
                 for when, kind, acct, cat, note, amt in rows]
        self.fill_table(self.tx_table, shown)
        self.fill_table(self.recent, [(when, typ, acct, cat, amt)
                                      for when, typ, acct, cat, note, amt in shown[:10]])
        self.fill_table(self.members_table, [(name,money(cents)) for name,cents in member_expenses(self.db)])
        transfer_rows = self.db.execute("""SELECT tr.recorded_at, a.name,b.name,tr.amount_cents,tr.note
            FROM transfers tr JOIN accounts a ON a.id=tr.from_account_id
            JOIN accounts b ON b.id=tr.to_account_id
            WHERE tr.profile_id=? ORDER BY tr.id DESC""",(pid,)).fetchall()
        self.fill_table(self.transfers_table,[(when,source,target,money(cents),note)
                                              for when,source,target,cents,note in transfer_rows])
        card_rows=cards(self.db,pid)
        self._row_ids['card']=[c[0] for c in card_rows]
        self.fill_table(self.card_table,[(name,str(cut),str(due),money(lim),money(debt)) for _,name,cut,due,lim,debt in card_rows])
        limit_total=sum(c[4] for c in card_rows)
        debt_total=sum(c[5] for c in card_rows)
        self.card_total_label.setText(money(debt_total))
        self.card_limit_label.setText(money(limit_total))
        self.card_available_label.setText(money(max(0,limit_total-debt_total)))
        self._selection_changed('card')
        self.fill_table(self.due_table,[(name,due,money(cents),cat,note) for name,due,cents,cat,note in upcoming(self.db,pid)])
        self.fill_table(self.dashboard_due,[(due,name,money(cents)) for name,due,cents,cat,note in upcoming(self.db,pid)[:7]])
        self.fill_table(self.shared_table,[(tid,date_,acct,cat,money(cents),splits) for tid,date_,acct,cat,cents,splits in shared_history(self.db)] if pid==2 else [])
        kmh_rows=overdraft(self.db,pid)
        self._row_ids['kmh']=[o[0] for o in kmh_rows]
        self.fill_table(self.kmh_table,[(name,money(limit),money(used),money(limit-used)) for oid,aid,name,limit,used in kmh_rows])
        self.kmh_limit_total.setText(money(sum(item[3] for item in kmh_rows)))
        self.kmh_used_total.setText(money(sum(item[4] for item in kmh_rows)))
        self.kmh_available_total.setText(money(sum(item[3]-item[4] for item in kmh_rows)))
        self._selection_changed('kmh')
        self.update_kmh_details()
        self.refresh_calendar()
        if hasattr(self,'rec_table'):
            self.fill_table(self.rec_table,[(i,n,'Fatura' if kind=='bill' else 'Abonelik',due,money(amt),cat) for i,n,kind,due,amt,cat in upcoming_items(self.db,pid,months_ahead=6)])
        self.fill_table(self.doc_table,[(did,name,TYPES.get(typ,typ),status,when) for did,name,typ,status,when,_ in list_docs(self.db,pid)])
        self.dashboard_info.setText('Kredi kartı kalan borcu: '+money(sum(c[-1] for c in cards(self.db,pid)))+'    |    Yaklaşan ödenmemiş taksit: '+str(len(upcoming(self.db,pid))))

    def update_account_details(self):
        row=self.acc_table.currentRow()
        ids=self._row_ids.get('account',[])
        if row < 0 or row >= len(ids):
            self.account_detail_heading.setText('Bir hesap seçerek ayrıntılarını görüntüleyin')
            self.account_logo.hide()
            self.account_detail_body.setText('Hesap türü, bakiye ve bağlı KMH bilgileri burada görünür.')
            return
        account_id=ids[row]
        record=next((a for a in accounts_with_balances(self.db,self.pid()) if a[0]==account_id),None)
        if not record:return
        _,name,kind,balance=record
        self.account_detail_heading.setText(name)
        from bank_logo_manager import LOGO_IDS
        bank=self._bank_for_text(name)
        self._set_detail_logo(self.account_logo, bank)
        detail=f'Hesap türü: {"Banka hesabı" if kind=="bank" else "Nakit / cüzdan"}  •  Güncel bakiye: {money(balance)}'
        linked=next((x for x in overdraft(self.db,self.pid()) if x[1]==account_id),None)
        if linked:
            _,_,_,limit,used=linked
            detail+=f'\nKMH limiti: {money(limit)}  •  Kullanılan: {money(used)}  •  Kullanılabilir: {money(limit-used)}'
        self.account_detail_body.setText(detail)

    def update_kmh_details(self):
        row=self.kmh_table.currentRow()
        ids=self._row_ids.get('kmh',[])
        if row < 0 or row >= len(ids):
            self.kmh_detail_heading.setText('Bir KMH hesabı seçin')
            self.kmh_logo.hide()
            self.kmh_detail_body.setText('Kullanım, kalan limit ve bağlı taksitli borçların özeti burada görünür.')
            return
        record=next((o for o in overdraft(self.db,self.pid()) if o[0]==ids[row]),None)
        if not record:return
        od_id,aid,name,limit,used=record
        loan_info=self.db.execute("""SELECT COUNT(*),COALESCE(SUM(i.principal_cents+i.interest_cents+i.tax_cents+i.fee_cents-i.paid_cents),0)
            FROM kmh_loans l JOIN kmh_installments i ON i.loan_id=l.id
            WHERE l.overdraft_id=?""",(od_id,)).fetchone()
        self.kmh_detail_heading.setText(name)
        from bank_logo_manager import LOGO_IDS
        bank=self._bank_for_text(name)
        self._set_detail_logo(self.kmh_logo, bank)
        self.kmh_detail_body.setText(f'Normal KMH limiti: {money(limit)}  •  Kullanılan: {money(used)}  •  Kullanılabilir: {money(limit-used)}\nTaksitli KMH satır sayısı: {loan_info[0]}  •  Kalan taksitli borç: {money(loan_info[1])}')

    def save_recurring(self):
        try:
            cents=int((Decimal(str(self.rec_amount.value()))*100).to_integral_value(rounding=ROUND_HALF_UP))
            add_item(self.db,self.pid(),self.rec_name.text(),self.rec_kind.currentData(),self.rec_category.text(),cents,self.rec_freq.currentData(),self.rec_due.date().toString('yyyy-MM-dd'))
            self.rec_name.clear();self.refresh()
        except Exception as exc: QMessageBox.warning(self,'Kayıt oluşturulamadı',str(exc))

    def pay_recurring(self):
        row=self.rec_table.currentRow()
        if row<0:return
        item_id=int(self.rec_table.item(row,0).text());due=self.rec_table.item(row,3).text()
        accounts=accounts_with_balances(self.db,self.pid())
        if not accounts:
            QMessageBox.warning(self,'Hesap gerekli','Ödeme yapmak için önce banka veya nakit hesabı ekleyin.');return
        # Hesap seçimi de mevcut uygulama içinde form olarak açılır.
        self._show_rec_account_select(item_id,due,accounts)

    def _show_rec_account_select(self,item_id,due,accounts):
        dlg=InlineDialog(self);dlg.setWindowTitle('Ödeme hesabını seç')
        form=QFormLayout(dlg);choice=QComboBox()
        for account_id,name,kind,balance in accounts:choice.addItem(f'{name}  ·  {money(balance)}',account_id)
        form.addRow('Ödeme hesabı',choice)
        controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(dlg.accept);controls.rejected.connect(dlg.reject);form.addRow(controls)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        if QMessageBox.question(self,'Ödemeyi onayla',f'{due} vadeli tutar, seçilen hesaba gider olarak kaydedilsin mi?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:pay_occurrence(self.db,self.pid(),item_id,due,choice.currentData());self.refresh()
        except Exception as exc:QMessageBox.warning(self,'Ödeme başarısız',str(exc))

    def pause_recurring(self):
        row=self.rec_table.currentRow()
        if row<0:return
        item_id=int(self.rec_table.item(row,0).text())
        if QMessageBox.question(self,'Düzenli ödemeyi durdur','Seçilen düzenli ödemenin gelecek dönemlerini durdurmak ister misiniz?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        try:set_active(self.db,self.pid(),item_id,False);self.refresh()
        except Exception as exc:QMessageBox.warning(self,'İşlem başarısız',str(exc))

    def refresh_calendar(self):
        if not hasattr(self,'calendar_table'):return
        from payment_calendar import summarize_calendar, filter_calendar
        rows=monthly_calendar(self.db,self.pid())
        summaries=summarize_calendar(rows)
        self.calendar_month_label.setText(money(summaries['this_month']))
        self.calendar_overdue_label.setText(money(summaries['overdue']))
        self.calendar_total_label.setText(money(summaries['total']))
        if hasattr(self,'calendar_recurring'):
            self.fill_table(self.calendar_recurring,[(name,'Fatura' if kind=='bill' else 'Abonelik',due,money(amt)) for _,name,kind,due,amt,_ in upcoming_items(self.db,self.pid(),months_ahead=3)])
        code=self.calendar_filter.currentData() or 'all'
        visible=filter_calendar(rows,code)
        today=date.today().isoformat()
        def status(due):
            return 'Gecikti' if due<today else ('Bugün' if due==today else 'Bekliyor')
        self.fill_table(self.calendar_table,[(iid,name,due,money(amount),status(due),note) for iid,name,due,amount,note in visible])

    def refresh_charts(self,pid):
        cat_rows=self.db.execute("""SELECT category,SUM(amount_cents) FROM (
            SELECT category,amount_cents FROM transactions WHERE profile_id=? AND kind='expense'
            UNION ALL SELECT p.category,p.total_cents FROM card_purchases p
            JOIN credit_cards c ON c.id=p.card_id WHERE c.profile_id=?)
            GROUP BY category ORDER BY SUM(amount_cents) DESC,category""",(pid,pid)).fetchall()
        def chart_slices(rows):
            rows=list(rows)
            if len(rows)>6:
                return rows[:5]+[('Diğer',sum(value for _,value in rows[5:]))]
            return rows
        self.category_chart.set_values(chart_slices([(str(k),v) for k,v in cat_rows]))
        hist=self.db.execute("""SELECT month,kind,SUM(amount_cents) FROM (
            SELECT substr(recorded_at,1,7) AS month,kind,amount_cents FROM transactions WHERE profile_id=?
            UNION ALL SELECT substr(p.purchase_date,1,7),'expense',p.total_cents
            FROM card_purchases p JOIN credit_cards c ON c.id=p.card_id WHERE c.profile_id=?)
            GROUP BY month,kind ORDER BY month DESC LIMIT 24""",(pid,pid)).fetchall()
        grouped={}
        for month,kind,value in hist:
            grouped.setdefault(month,[0,0])[0 if kind=='income' else 1]+=value
        self.trend_chart.set_values([(month, vals[0],vals[1]) for month,vals in sorted(grouped.items())[-6:]])
        accts=accounts_with_balances(self.db,pid)
        self.asset_chart.set_values(chart_slices(sorted([(name,balance) for _,name,kind,balance in accts if balance>0],key=lambda row:row[1],reverse=True)))

    def import_document(self):
        filename,_=QFileDialog.getOpenFileName(self,'Banka veya bordro belgesi seç','','Belgeler (*.pdf *.csv *.xlsx *.txt)')
        if not filename:return
        d,form=self._form('Belge türünü seç')
        typ=QComboBox()
        for code,label in TYPES.items():typ.addItem(label,code)
        form.addRow('Belge türü',typ)
        self._buttons(d,form)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try:
            doc_id,created,parsed=stage(self.db,self.pid(),filename,typ.currentData())
            note='\n'.join(parsed['warnings']) or 'Belge incelemeye alındı.'
            QMessageBox.information(self,'Belge alındı',('Yeni kayıt' if created else 'Bu belge daha önce yüklendi')+f' (#{doc_id})\n'+note)
            self.refresh()
            for r in range(self.doc_table.rowCount()):
                if int(self.doc_table.item(r,0).text())==doc_id:
                    self.doc_table.selectRow(r)
                    break
            if created and parsed['type'] in ('payslip','invoice','statement'):
                self.select_page(9)
                for r in range(self.doc_table.rowCount()):
                    if int(self.doc_table.item(r,0).text())==doc_id:
                        self.doc_table.selectRow(r)
                        break
                self.post_document_entry()
        except Exception as exc:QMessageBox.warning(self,'Belge alınamadı',str(exc))

    def preview_document_rows(self):
        import json
        row=self.doc_table.currentRow()
        if row<0:
            self.fill_table(self.doc_preview,[])
            return
        doc_id=int(self.doc_table.item(row,0).text())
        dbrow=self.db.execute('SELECT extracted_json FROM imported_documents WHERE id=? AND profile_id=?',(doc_id,self.pid())).fetchone()
        if not dbrow:return
        data=json.loads(dbrow[0]);entries=[]
        for item in data.get('candidates',[]):
            if 'installment' in item:
                amount=item['total_cents'];desc='Taksit '+str(item['installment'])
            else:
                amount=item['amount_cents'];desc=item['description']
            entries.append((item['source_line'],item['date'],desc,money(amount),'Kontrol gerekli'))
        self.fill_table(self.doc_preview,entries)
        warnings=data.get('warnings',[])
        if warnings: self.doc_preview.setToolTip('\n'.join(warnings))

    def post_salary_document(self):
        self.post_document_entry()

    def post_document_entry(self):
        row=self.doc_table.currentRow()
        if row<0:
            QMessageBox.information(self,'Belge seç','Önce tabloda bir belge seçin.');return
        doc_id=int(self.doc_table.item(row,0).text())
        doc=self.db.execute('SELECT doc_type,status,extracted_json FROM imported_documents WHERE id=? AND profile_id=?',(doc_id,self.pid())).fetchone()
        if not doc or doc[0] not in ('payslip','invoice','statement') or doc[1]=='posted':
            QMessageBox.warning(self,'İşlem yapılamadı','Bekleyen bordro, fatura veya ekstre satırı seçin.');return
        import json
        parsed=json.loads(doc[2]);accs=accounts_with_balances(self.db,self.pid())
        typ=doc[0]
        choices=cards(self.db,self.pid()) if typ=='statement' else accs
        if not choices:QMessageBox.warning(self,'Hesap / kart gerekli','Önce ilgili banka hesabını veya kredi kartını ekleyin.');return
        d,form=self._form('Belgeden finans kaydı · kontrol ve onay')
        info=QLabel('Ekstre alışverişi kart borcuna eklenir; banka bakiyesinden para düşülmez. Ödeme, iade, devir ve mevcut planın taksit satırlarını aktarmayın.' if typ=='statement' else 'Yalnız gerçekleşmiş ödeme / hesaba geçen maaşı onaylayın. Ödenmemiş fatura henüz gider değildir.')
        info.setWordWrap(True);form.addRow(info)
        account=QComboBox()
        for item in choices:account.addItem(item[1],item[0])
        amount=QDoubleSpinBox();amount.setMaximum(100000000);amount.setDecimals(2)
        amount.setSuffix(' ₺');amount.setValue(parsed['fields'].get('net' if typ=='payslip' else 'total',0)/100)
        period=QLineEdit(str(parsed['fields'].get('period','Dönem belirtilmedi')))
        category=QLineEdit('Maaş' if typ=='payslip' else ('Faturalar' if typ=='invoice' else 'Kart alışverişi'))
        fields=parsed['fields']
        desc=QLineEdit(('Fatura: '+str(fields.get('issuer',''))+' '+str(fields.get('invoice_number',''))).strip() if typ=='invoice' else 'Bordro')
        when=QDateEdit();when.setCalendarPopup(True);when.setDisplayFormat('dd.MM.yyyy');when.setDate(QDate.currentDate())
        source=QComboBox()
        if typ=='statement':
            linked={r[0] for r in self.db.execute('SELECT row_key FROM document_posting_links WHERE document_id=?',(doc_id,))}
            candidates=[x for x in parsed.get('candidates',[]) if str(x['source_line']) not in linked and x['amount_cents']>0]
            if not candidates:
                QMessageBox.information(self,'Satır bulunamadı','Aktarılabilir alışveriş satırı yok. Metin içeren PDF veya Tarih;Açıklama;Tutar sütunlu CSV kullanın. Ekstre toplamı gider olarak aktarılmaz.');return
            for item in candidates:source.addItem(f"{item['date']} · {item['description']} · {money(item['amount_cents'])}",item)
            def choose_line(*_):
                item=source.currentData();amount.setValue(item['amount_cents']/100)
                desc.setText(item['description']);when.setDate(QDate.fromString(item['date'],'yyyy-MM-dd'))
            source.currentIndexChanged.connect(choose_line);choose_line()
            form.addRow('Alışveriş satırı',source)
        form.addRow('Kredi kartı' if typ=='statement' else 'Banka / nakit hesabı',account)
        form.addRow('Tutar',amount);form.addRow('Alışveriş tarihi' if typ=='statement' else 'Hesaba geçiş / ödeme tarihi',when)
        form.addRow('Kategori',category)
        if typ=='payslip':form.addRow('Bordro dönemi',period)
        else:form.addRow('Açıklama',desc)
        paid=QCheckBox('Bilgileri kontrol ettim; bu bir alışveriştir, ödeme/iade/devir değildir' if typ=='statement' else 'Ödemenin gerçekleştiğini ve bilgilerin doğru olduğunu onaylıyorum')
        form.addRow(paid)
        duplicate_note=QLabel('Aynı tarih, tutar ve açıklamayla kayıt varsa mevcut kayda bağlanır; tekrar gider/gelir oluşturulmaz.')
        duplicate_note.setWordWrap(True);form.addRow(duplicate_note)
        self._buttons(d,form)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try:
            _,created=approve_document_entry(self.db,self.pid(),doc_id,
                account_id=account.currentData() if typ!='statement' else None,
                card_id=account.currentData() if typ=='statement' else None,
                cents=from_spin(amount),day=when.date().toString('yyyy-MM-dd'),
                category=category.text(),description=desc.text(),confirmed=paid.isChecked(),
                source_line=source.currentData()['source_line'] if typ=='statement' else None,period=period.text())
            self.refresh()
            QMessageBox.information(self,'Belge işlendi','Finans kaydı oluşturuldu.' if created else 'Mevcut kayda bağlandı; tekrar kayıt oluşturulmadı.')
        except Exception as exc:QMessageBox.warning(self,'Kayıt oluşturulamadı',str(exc))

    def create_account(self):
        dialog = AddAccountDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            kind = dialog.kind.currentData()
            bank = dialog.bank.currentText().strip() if kind == 'bank' else ''
            if kind == 'bank' and not bank:
                raise ValueError('Lütfen bir banka seçin veya banka adını yazın.')
            name = dialog.name.text().strip() or (f'{bank} - Vadesiz Hesap' if bank else 'Cüzdanım')
            init_account_bank_catalog(self.db)
            add_account(self.db, self.pid(), name, kind, from_spin(dialog.balance))
            if bank:
                # Find the account just created in this profile; keep the old accounts schema intact.
                account_id = self.db.execute('SELECT MAX(id) FROM accounts WHERE profile_id=?', (self.pid(),)).fetchone()[0]
                with self.db:
                    self.db.execute('INSERT INTO account_bank_details(account_id,bank_name) VALUES(?,?)', (account_id,bank))
            self.refresh()
        except (ValueError, sqlite3.IntegrityError) as exc:
            QMessageBox.warning(self, 'Hesap eklenemedi', str(exc))

    def create_transaction(self):
        accs = accounts_with_balances(self.db, self.pid())
        if not accs:
            QMessageBox.information(self, 'Önce hesap ekleyin', 'İşlem eklemek için önce Hesaplar bölümünden bir hesap oluşturun.')
            return
        dialog = AddTransactionDialog(accs, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            add_transaction(self.db, self.pid(), dialog.account.currentData(), dialog.kind.currentData(),
                            dialog.category.currentText(), dialog.description.text(), from_spin(dialog.amount))
            self.refresh()
        except (ValueError, sqlite3.IntegrityError) as exc:
            QMessageBox.warning(self, 'İşlem eklenemedi', str(exc))

    def create_member(self):
        d, form = self._form('Yeni aile üyesi')
        name = QLineEdit()
        name.setPlaceholderText('Aile üyesinin adı')
        form.addRow('Adı', name)
        self._buttons(d, form)
        if d.exec() == QDialog.DialogCode.Accepted:
            try:
                add_member(self.db, name.text().strip())
                self.refresh()
            except (ValueError, sqlite3.IntegrityError) as exc:
                QMessageBox.warning(self, 'Üye eklenemedi', str(exc))

    def create_shared_expense(self):
        if self.pid() != 2:
            QMessageBox.information(self, 'Aile çalışma alanı', 'Önce üstteki çalışma alanından Aile seçin.')
            return
        members = get_members(self.db)
        accounts = accounts_with_balances(self.db, self.pid())
        if not members or not accounts:
            QMessageBox.information(self, 'Eksik bilgi', 'Önce en az bir aile üyesi ve Aile alanında hesap ekleyin.')
            return
        d = InlineDialog(self)
        d.setWindowTitle('Ortak gider ve paylaşım')
        form = QFormLayout(d)
        acc = QComboBox()
        for row in accounts:
            acc.addItem(row[1],row[0])
        cat = QLineEdit('Market')
        note = QLineEdit()
        total = QDoubleSpinBox(); total.setRange(0.01,100000000); total.setDecimals(2); total.setValue(100); total.setSuffix(' ₺')
        form.addRow('Ödeme hesabı', acc)
        form.addRow('Kategori', cat)
        form.addRow('Açıklama', note)
        form.addRow('Toplam tutar', total)
        spins = []
        for mid, name in members:
            spin = QDoubleSpinBox(); spin.setRange(0,100000000); spin.setDecimals(2); spin.setSuffix(' ₺')
            form.addRow(name+' payı',spin)
            spins.append((mid,spin))
        def equalize():
            cents = from_spin(total)
            q,r = divmod(cents,len(spins))
            for idx,(_,spin) in enumerate(spins):
                spin.setValue((q+(1 if idx<r else 0))/100)
        auto = QPushButton('Eşit paylaştır')
        auto.clicked.connect(equalize)
        form.addRow(auto)
        equalize()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(d.accept); buttons.rejected.connect(d.reject)
        form.addRow(buttons)
        if d.exec() == QDialog.DialogCode.Accepted:
            try:
                add_shared_expense(self.db,self.pid(),acc.currentData(),cat.text(),note.text(),from_spin(total),
                                   {mid:from_spin(spin) for mid,spin in spins})
                self.refresh()
            except (ValueError,sqlite3.IntegrityError) as exc:
                QMessageBox.warning(self,'Ortak gider eklenemedi',str(exc))

    def create_transfer(self):
        accounts = accounts_with_balances(self.db,self.pid())
        if len(accounts)<2:
            QMessageBox.information(self,'Hesap gerekli','Transfer için aynı çalışma alanında iki hesap ekleyin.')
            return
        d=InlineDialog(self); d.setWindowTitle('Hesaplar arası transfer'); form=QFormLayout(d)
        src=QComboBox(); target=QComboBox()
        for row in accounts:
            src.addItem(row[1],row[0]); target.addItem(row[1],row[0])
        target.setCurrentIndex(1)
        amount=QDoubleSpinBox(); amount.setRange(0.01,100000000); amount.setDecimals(2); amount.setValue(100); amount.setSuffix(' ₺')
        note=QLineEdit()
        for label,widget in [('Gönderen',src),('Alıcı',target),('Tutar',amount),('Açıklama',note)]:
            form.addRow(label,widget)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject);form.addRow(buttons)
        if d.exec() == QDialog.DialogCode.Accepted:
            try:
                transfer(self.db,self.pid(),src.currentData(),target.currentData(),from_spin(amount),note.text())
                self.refresh()
            except (ValueError,sqlite3.IntegrityError) as exc:
                QMessageBox.warning(self,'Transfer yapılamadı',str(exc))

    def _form(self,title):
        d=InlineDialog(self);d.setWindowTitle(title);f=QFormLayout(d)
        return d,f

    def _buttons(self,d,f):
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        b.button(QDialogButtonBox.StandardButton.Ok).setText('Onayla')
        b.button(QDialogButtonBox.StandardButton.Cancel).setText('İptal')
        b.accepted.connect(d.accept);b.rejected.connect(d.reject);f.addRow(b)

    def _amount(self,initial=100):
        x=QDoubleSpinBox();x.setRange(0.01,100000000);x.setDecimals(2);x.setValue(initial);x.setSuffix(' ₺');return x

    def download_bank_logos(self, manual=False):
        """Eksik logoları indirmeyi arka planda dener; kullanıcıyı modal pencereyle bölmez."""
        if getattr(self, '_logo_worker', None) and self._logo_worker.isRunning():
            return
        from bank_logo_manager import missing_logos
        if not manual and not missing_logos():
            self.logo_status.hide()
            return
        self.logo_status.setText('Banka logoları güncelleniyor…')
        self.logo_status.show()
        self._logo_worker = LogoDownloadWorker(self)
        self._logo_worker.finished_result.connect(self._bank_download_done)
        self._logo_worker.start()

    def _bank_download_done(self, n, existing, errors):
        self.logo_status.hide()
        self._refresh_bank_icons()
        if errors:
            self.statusBar().showMessage(f'{len(errors)} banka logosu indirilemedi; sonraki açılışta yeniden denenecek.', 9000)
        elif n:
            self.statusBar().showMessage(f'{n} banka logosu indirildi.', 5000)
        else:
            self.statusBar().showMessage('Banka logoları güncel.', 3500)

    def _build_bank_aliases(self):
        from bank_logo_manager import LOGO_IDS
        aliases = {name: {name} for name in LOGO_IDS}
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'account_bank_details' in tables:
            for name, bank in self.db.execute(
                    'SELECT a.name,b.bank_name FROM accounts a JOIN account_bank_details b ON b.account_id=a.id WHERE a.profile_id=?',
                    (self.pid(),)):
                aliases.setdefault(name, set()).add(bank)
        if 'card_catalog_links' in tables:
            for name, bank in self.db.execute(
                    'SELECT c.name,l.bank FROM credit_cards c JOIN card_catalog_links l ON l.card_id=c.id WHERE c.profile_id=?',
                    (self.pid(),)):
                aliases.setdefault(name, set()).add(bank)
        return aliases

    def _bank_for_text(self, text):
        # Prefer saved bank metadata, including custom account/card nicknames.
        aliases = getattr(self, '_bank_aliases', {})
        folded = text.casefold()
        for label in sorted(aliases, key=len, reverse=True):
            key = label.casefold()
            if folded == key or any(folded.startswith(key + sep) for sep in (' (', ' · ', ' — ', ' - ')):
                banks = aliases[label]
                return next(iter(banks)) if len(banks) == 1 else ''
        return ''

    def _decorate_bank_widgets(self, root):
        for widget in root.findChildren(QComboBox):
            found = False
            for index in range(widget.count()):
                data = widget.itemData(index)
                bank = data[0] if isinstance(data, tuple) and len(data) == 2 and isinstance(data[0], str) else self._bank_for_text(widget.itemText(index))
                if bank:
                    widget.setItemIcon(index, self._bank_icon(bank))
                    found = True
            if found:
                widget.setIconSize(QSize(110, 24))
                widget.setMaxVisibleItems(5)
                widget.setMaximumWidth(420)
                widget.view().setIconSize(QSize(110, 24))
                widget.view().setStyleSheet("QListView {padding:3px 5px;outline:0;} QListView::item {min-height:32px;padding:0px 6px;}")

    def _refresh_bank_icons(self):
        self._decorate_bank_widgets(self)
        self.refresh()
        self.update_account_details()
        self.update_kmh_details()
        if hasattr(self, 'card_table'):
            row = self.card_table.currentRow()
            ids = self._row_ids.get('card', [])
            if 0 <= row < len(ids):
                self._show_selected_card(ids[row])

    def _set_detail_logo(self, target, bank):
        icon = self._bank_icon(bank)
        pixmap = icon.pixmap(QSize(110, 24), self.devicePixelRatioF())
        target.setFixedSize(110, 34)
        target.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        target.setScaledContents(False)
        target.setPixmap(pixmap)
        target.setVisible(bool(bank))

    def _bank_icon(self, bank):
        # Optional official logo assets supplied by the user; do not impersonate logos.
        source = logo_path(bank)
        if source:
            icon = menu_icon(source)
            if not icon.isNull():
                return icon
        # Neutral initials badge, NOT a bank trademark/logo.
        pix = QPixmap(330, 72)
        pix.setDevicePixelRatio(3)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor('#50647e'))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(4, 1, 22, 22, 5, 5)
        painter.setPen(QColor('#ffffff'))
        font = QFont('Arial', 9, QFont.Weight.Bold)
        painter.setFont(font)
        initials = ''.join(word[0] for word in bank.split()[:2]).upper()
        painter.drawText(QRectF(4, 1, 22, 22), Qt.AlignmentFlag.AlignCenter, initials)
        painter.end()
        return QIcon(pix)

    def _inline_form(self,title):
        if getattr(self,'inline_page',None) is not None:
            self.stack.removeWidget(self.inline_page);self.inline_page.deleteLater()
        d=QWidget();self.inline_page=d;v=QVBoxLayout(d);heading=QLabel(title);heading.setObjectName('heading');v.addWidget(heading)
        f=QFormLayout();v.addLayout(f);v.addStretch();self.stack.addWidget(d);self.stack.setCurrentWidget(d)
        return d,f

    def _inline_buttons_and_wait(self,d,f):
        # Asynchronous save behavior: form save callback is attached by the caller;
        # nested event loop keeps this prototype compatible with existing handlers.
        from PySide6.QtCore import QEventLoop
        loop=QEventLoop();answer={'saved':False}
        save=QPushButton('Kartı kaydet');cancel=QPushButton('İptal')
        def finish(ok):
            answer['saved']=ok
            self.stack.setCurrentIndex(5)
            loop.quit()
        save.clicked.connect(lambda:finish(True));cancel.clicked.connect(lambda:finish(False))
        bar=QHBoxLayout();bar.addWidget(save);bar.addWidget(cancel);f.addRow(bar)
        self._decorate_bank_widgets(d)
        loop.exec()
        self.stack.removeWidget(d)
        d.deleteLater()
        self.inline_page=None
        return answer['saved']

    def new_overdraft(self):
        a=[x for x in accounts_with_balances(self.db,self.pid()) if x[2]=='bank']
        if not a:QMessageBox.information(self,'Banka hesabı','Önce Hesaplar bölümünden banka hesabı ekleyin.');return
        d,f=self._form('Banka hesabı KMH limiti');account=QComboBox()
        for x in a:account.addItem(x[1],x[0])
        limit=self._amount(10000);f.addRow('Banka hesabı',account);f.addRow('KMH limiti',limit);self._buttons(d,f)
        if d.exec()==QDialog.DialogCode.Accepted:
            try:set_overdraft(self.db,self.pid(),account.currentData(),from_spin(limit));self.refresh()
            except Exception as e:QMessageBox.warning(self,'KMH',str(e))

    def kmh_draw_repay(self):
        os=overdraft(self.db,self.pid())
        if not os:QMessageBox.information(self,'KMH','Önce KMH tanımlayın.');return
        d,f=self._form('KMH kullan / kapat');od=QComboBox()
        for x in os:od.addItem(x[2]+' (Kullanılan '+money(x[4])+')',x[0])
        kind=QComboBox();kind.addItem('KMH kullan (borçlan)', 'draw');kind.addItem('KMH anaparasını kapat','repay')
        amount=self._amount();note=QLineEdit()
        for label,w in [('Hesap',od),('İşlem',kind),('Tutar',amount),('Açıklama',note)]:f.addRow(label,w)
        self._buttons(d,f)
        if d.exec()==QDialog.DialogCode.Accepted:
            try:use_overdraft(self.db,self.pid(),od.currentData(),from_spin(amount),kind.currentData(),note.text());self.refresh()
            except Exception as e:QMessageBox.warning(self,'KMH',str(e))

    def new_kmh_loan(self):
        os=overdraft(self.db,self.pid())
        if not os:QMessageBox.information(self,'KMH','Önce KMH limiti ekleyin.');return
        d,f=self._form('Taksitli KMH (banka planını esas alın)');od=QComboBox()
        for x in os:od.addItem(x[2],x[0])
        principal=self._amount(10000);count=QComboBox()
        for i in range(1,61):count.addItem(str(i),i)
        month_total=self._amount(1900);first=QDateEdit();first.setCalendarPopup(True);first.setDate(date.today()+timedelta(days=30))
        note=QLineEdit()
        for name,w in [('Banka hesabı',od),('Anapara',principal),('Taksit sayısı',count),('Bankanın aylık toplam taksiti',month_total),('İlk ödeme tarihi',first),('Açıklama',note)]:f.addRow(name,w)
        info=QLabel('Bu prototipte toplam geri ödeme farkı vergi/faiz ayrışımı olmadan ücret sütununda gösterilir. Bankanın resmî planına göre doğrulayın.');info.setWordWrap(True);f.addRow(info)
        self._buttons(d,f)
        if d.exec()==QDialog.DialogCode.Accepted:
            try:
                n=count.currentData();p=from_spin(principal);monthly=from_spin(month_total)
                if monthly*n<p:raise ValueError('Toplam taksitler anaparadan az olamaz.')
                start=first.date().toPython();q,r=divmod(p,n);total_extra=monthly*n-p
                schedule=[]
                for i in range(n):
                    pr=q+(1 if i<r else 0)
                    extra=total_extra//n+(1 if i<total_extra%n else 0)
                    schedule.append((month_add(start,i).isoformat(),pr,0,0,extra))
                add_installment_loan(self.db,self.pid(),od.currentData(),p,schedule,note.text());self.refresh()
            except Exception as e:QMessageBox.warning(self,'KMH taksiti',str(e))

    def kmh_pay(self):
        row=self.calendar_table.currentRow()
        if row<0:QMessageBox.information(self,'Taksit','Önce ödeme takviminden bir taksit seçin.');return
        iid=int(self.calendar_table.item(row,0).text());accounts=accounts_with_balances(self.db,self.pid())
        if not accounts:return
        d,f=self._form('KMH taksiti öde');a=QComboBox()
        for x in accounts:a.addItem(x[1],x[0])
        amount=self._amount();f.addRow('Ödeyen hesap',a);f.addRow('Tutar',amount);self._buttons(d,f)
        if d.exec()==QDialog.DialogCode.Accepted:
            try:pay_installment(self.db,self.pid(),iid,a.currentData(),from_spin(amount));self.refresh()
            except Exception as e:QMessageBox.warning(self,'Taksit ödemesi',str(e))

    def new_card(self):
        d,f=self._inline_form('Katalogdan kredi kartı ekle')
        catalog=load_catalog()
        query=QLineEdit();query.setPlaceholderText('Kart veya banka ara…')
        bank=QComboBox();bank.addItem('Tüm bankalar','')
        for v in sorted({x['bank'] for x in catalog}):bank.addItem(self._bank_icon(v),v,v)
        bank.setIconSize(QSize(110,24))
        model=QComboBox()
        network=QComboBox()
        for key in ('Bilinmiyor / henüz seçilmedi', 'Visa', 'Mastercard', 'TROY', 'Diğer'):
            network.addItem(key, '' if key.startswith('Bilinmiyor') else key)
        manual=QCheckBox('Kartım listede yok, elle tanımlayacağım')
        custom_bank=QLineEdit();custom_card=QLineEdit();nickname=QLineEdit()
        cut=QComboBox();due=QComboBox()
        for i in range(1,32):cut.addItem(str(i),i);due.addItem(str(i),i)
        def auto_due():
            closing=date.today().replace(day=min(cut.currentData(), __import__('calendar').monthrange(date.today().year,date.today().month)[1]))
            nextday=closing_due(closing.isoformat())
            due.setCurrentIndex(nextday.day-1)
            due_tip.setText('Örnek: '+closing.strftime('%d.%m.%Y')+' → '+nextday.strftime('%d.%m.%Y')+' (en az 10 gün; bankanı kontrol et)')
        due_tip=QLabel(); due_tip.setWordWrap(True)
        cut.currentIndexChanged.connect(auto_due)
        auto_due()
        lim=self._amount(10000)
        info=QLabel('Katalog başlangıç listesidir; bankanın güncel tekliflerini doğrulayın.')
        info.setWordWrap(True)
        for label,w in [('Banka filtresi',bank),('Ara',query),('Kart modeli',model),('Ödeme ağı (kartınızda yazan)',network),('',manual),('Banka (elle)',custom_bank),('Kart modeli (elle)',custom_card),('Kart takma adı (isteğe bağlı)',nickname),('Hesap kesim günü',cut),('Son ödeme günü (değiştirilebilir)',due),('',due_tip),('Limit',lim),('',info)]: f.addRow(label,w)
        def update_models():
            previous=model.currentData();model.clear()
            for c in search_catalog(catalog,query.text(),bank.currentData()):
                status=' • doğrulandı' if c['verified'] else ' • kontrol edin'
                model.addItem(self._bank_icon(c['bank']),c['bank']+' — '+c['card']+status,(c['bank'],c['card']))
            if previous:
                idx=model.findData(previous)
                if idx>=0:model.setCurrentIndex(idx)
            self._decorate_bank_widgets(d)
        def update_manual():
            flag=manual.isChecked();custom_bank.setEnabled(flag);custom_card.setEnabled(flag)
            query.setEnabled(not flag);bank.setEnabled(not flag);model.setEnabled(not flag)
        bank.currentIndexChanged.connect(update_models);query.textChanged.connect(update_models)
        manual.toggled.connect(update_manual);update_models();update_manual()
        if not self._inline_buttons_and_wait(d,f):return
        if True:
            if manual.isChecked():
                selected_bank=custom_bank.text().strip();selected_card=custom_card.text().strip()
            else:
                selected=model.currentData()
                if not selected:QMessageBox.warning(self,'Kart seçilmedi','Lütfen katalogdan kart seçin veya elle tanımlayın.');return
                selected_bank,selected_card=selected
            if not selected_bank or not selected_card:QMessageBox.warning(self,'Eksik bilgi','Banka ve kart modeli gerekli.');return
            label=nickname.text().strip() or selected_card
            try:
                create_card(self.db,self.pid(),label,cut.currentData(),due.currentData(),from_spin(lim))
                # Extra metadata is separate: existing v0.5 balances/installments remain untouched.
                card_id=self.db.execute('SELECT id FROM credit_cards WHERE profile_id=? AND name=? ORDER BY id DESC LIMIT 1',(self.pid(),label)).fetchone()[0]
                with self.db:
                    self.db.execute('INSERT INTO card_catalog_links(card_id,bank,card_model,payment_network) VALUES (?,?,?,?)',(card_id,selected_bank,selected_card,network.currentData()))
                self.refresh()
            except (ValueError,sqlite3.IntegrityError) as ex:QMessageBox.warning(self,'Kart eklenemedi',str(ex))

    def new_purchase(self):
        cc=cards(self.db,self.pid())
        if not cc:QMessageBox.information(self,'Kart gerekli','Önce kart ekleyin.');return
        d,f=self._form('Taksitli kart alışverişi');card=QComboBox()
        for c in cc:card.addItem(c[1],c[0])
        cat=QLineEdit('Alışveriş');note=QLineEdit();amount=self._amount();n=QComboBox()
        for i in range(1,61):n.addItem(str(i),i)
        for label,w in [('Kart',card),('Kategori',cat),('Açıklama',note),('Toplam alışveriş',amount),('Taksit sayısı',n)]:f.addRow(label,w)
        self._buttons(d,f)
        if d.exec()==QDialog.DialogCode.Accepted:
            try:purchase(self.db,self.pid(),card.currentData(),cat.text(),note.text(),from_spin(amount),n.currentData());self.refresh()
            except (ValueError,sqlite3.IntegrityError) as ex:QMessageBox.warning(self,'Alışveriş kaydedilemedi',str(ex))

    def new_card_payment(self):
        cc=[c for c in cards(self.db,self.pid()) if c[-1]>0];aa=accounts_with_balances(self.db,self.pid())
        if not cc or not aa:QMessageBox.information(self,'Kart ve hesap gerekli','Borcu olan kart ve ödeme yapılacak nakit/banka hesabı gerekli.');return
        d,f=self._form('Kart borcu öde');card=QComboBox();account=QComboBox();amount=self._amount()
        for c in cc:card.addItem(c[1]+' ('+money(c[-1])+')',c[0])
        for a in aa:account.addItem(a[1]+' ('+money(a[3])+')',a[0])
        for label,w in [('Kart',card),('Ödeyen hesap',account),('Ödeme tutarı',amount)]:f.addRow(label,w)
        self._buttons(d,f)
        if d.exec()==QDialog.DialogCode.Accepted:
            try:pay_card(self.db,self.pid(),card.currentData(),account.currentData(),from_spin(amount));self.refresh()
            except (ValueError,sqlite3.IntegrityError) as ex:QMessageBox.warning(self,'Ödeme kaydedilemedi',str(ex))

    def correct_split(self):
        if self.pid()!=2 or self.shared_table.currentRow()<0:QMessageBox.information(self,'İşlem seçin','Aile alanında geçmişten bir gider seçin.');return
        tid=int(self.shared_table.item(self.shared_table.currentRow(),0).text())
        members=get_members(self.db)
        previous=dict(self.db.execute('SELECT member_id,amount_cents FROM expense_splits WHERE transaction_id=?',(tid,)).fetchall())
        total=self.db.execute('SELECT amount_cents FROM transactions WHERE id=?',(tid,)).fetchone()[0]
        d,f=self._form('Gider paylaşımını düzelt');inputs=[]
        for mid,name in members:
            spin=QDoubleSpinBox();spin.setRange(0,100000000);spin.setDecimals(2);spin.setValue(previous.get(mid,0)/100);f.addRow(name,spin);inputs.append((mid,spin))
        f.addRow(QLabel('Toplam pay '+money(total)+' olmalı. İşlem tutarı değişmez.'))
        self._buttons(d,f)
        if d.exec()==QDialog.DialogCode.Accepted:
            try:edit_shared_split(self.db,tid,{mid:from_spin(w) for mid,w in inputs});self.refresh()
            except (ValueError,sqlite3.IntegrityError) as ex:QMessageBox.warning(self,'Paylar kaydedilemedi',str(ex))

    def toggle_theme(self):
        self.dark = not self.dark
        self.apply_theme()

    def apply_theme(self):
        if self.dark:
            background='#09172b'; surface='#122a43'; card='#16314c'; ink='#edf8ff'; border='#244662'; muted='#aac2d3'
        else:
            background='#edf5fa'; surface='#ffffff'; card='#ffffff'; ink='#102942'; border='#dceaf2'; muted='#597b91'
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{background:{background};color:{ink};font-family:'Segoe UI';font-size:13px;}}
            QWidget#sidebar {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #031d36,stop:0.6 #083452,stop:1 #065365);border:1px solid #275d79;border-radius:18px;color:white;}}
            QScrollArea#sidebarMenuScroll {{background:transparent;border:none;}}
            QWidget#sidebarMenuContent {{background:#092d49;}}
            QScrollArea#sidebarMenuScroll QScrollBar:vertical {{background:#092d49;width:7px;margin:0;}}
            QScrollArea#sidebarMenuScroll QScrollBar::handle:vertical {{background:#38718b;min-height:32px;border-radius:3px;}}
            QScrollArea#sidebarMenuScroll QScrollBar::add-line:vertical,QScrollArea#sidebarMenuScroll QScrollBar::sub-line:vertical {{height:0;}}
            QWidget#brandPanel {{background:#092d49;border:1px solid #174763;border-radius:12px;}}
            QWidget#brandPanel QLabel {{background:transparent;color:#ffffff;}}
            QWidget#brandPanel QLabel#mascotAvatar {{background:#ffffff;border:1px solid #d6f5f3;border-radius:30px;}}
            QWidget#sidebar QLabel {{color:#eefbff;background:transparent;}}
            QWidget#sidebar QPushButton {{color:#eefbff;background:#123e5c;border:1px solid #275773;}}
            QWidget#sidebar QPushButton:disabled {{color:#8daabd;background:#0b304d;border:1px solid #16415c;}}
            QWidget#sidebar QComboBox {{color:#eefbff;background:#123e5c;}}
            QFrame#cardMetric, QFrame#cardDetails {{background:{card};border:1px solid {border};border-radius:14px;}}
            QLabel#metricCaption {{color:{muted};font-weight:700;font-size:11px;}}
            QLabel#metricNumber {{font-size:23px;font-weight:800;color:{ink};}}
            QLabel#cardDetailHeading {{font-size:16px;font-weight:800;color:{ink};}}
            QGroupBox {{background:{card};border:1px solid {border};border-radius:16px;margin-top:15px;padding:14px;font-weight:600;}}
            QGroupBox::title {{subcontrol-origin:margin;left:14px;padding:0 7px;}}
            QPushButton {{background:{surface};border:1px solid {border};padding:10px 14px;border-radius:9px;font-weight:600;}}
            QPushButton:hover {{background:#087f94;color:white;}}
            QPushButton:disabled {{color:#8298a9;}}
            QPushButton[nav='true'] {{text-align:left;padding:9px 12px;background:transparent;border:0;border-radius:10px;min-height:21px;}}
            QPushButton[nav='true']:hover {{background:#066e85;}}
            QComboBox,QLineEdit,QDoubleSpinBox,QDateEdit {{background:{surface};border:1px solid {border};border-radius:9px;padding:9px;}}
            QComboBox::drop-down, QDateEdit::drop-down {{subcontrol-origin:padding;subcontrol-position:top right;width:33px;border:0;border-left:1px solid {border};border-top-right-radius:9px;border-bottom-right-radius:9px;}}
            QComboBox::down-arrow, QDateEdit::down-arrow {{image:url(\"{(Path(__file__).resolve().parent / 'assets' / 'chevron-down.svg').as_posix()}\");width:14px;height:14px;}}
            QComboBox QAbstractItemView {{selection-background-color:#0e9bab;selection-color:#ffffff;outline:0;}}
            QComboBox#bankSelection {{padding-left:11px;}}
            QTableWidget {{background:{card};alternate-background-color:{surface};border:1px solid {border};border-radius:10px;gridline-color:{border};selection-background-color:#087f94;}}
            QHeaderView::section {{background:{surface};color:{ink};border:0;border-bottom:1px solid {border};padding:10px;font-weight:600;}}
            QLabel#brand {{font-size:21px;font-weight:800;color:white;background:transparent;}}
            QLabel#sidebarCaption {{color:#a6d2e1;font-weight:700;font-size:10px;}}
            QLabel#navGroupHeading {{color:#77bed0;font-size:10px;font-weight:800;padding:10px 10px 2px 10px;background:transparent;}}
            QLabel#sidebarFooter {{color:#b7e8ed;background:#123e5c;border-radius:10px;padding:13px;}}
            QLabel#profileBadge {{background:{surface};border:1px solid {border};border-radius:10px;padding:11px;}}
            QLineEdit#globalSearch {{border-radius:16px;padding:12px 18px;background:{surface};}}
            QLabel#slogan {{color:#d9f5f6;font-size:10px;font-style:italic;}}
            QLabel#heading {{font-size:27px;font-weight:800;}}
            QLabel#stat {{font-size:24px;font-weight:800;background:transparent;color:{ink};}}
            QFrame#overviewCard {{background:{card};border:1px solid {border};border-top:4px solid #19c8bc;border-radius:15px;}}
            QFrame#overviewCard[tone='rose'] {{border-top-color:#fb6685;}}
            QFrame#overviewCard[tone='green'] {{border-top-color:#32c68b;}}
            QFrame#overviewCard[tone='orange'] {{border-top-color:#ff9a43;}}
            QFrame#overviewCard[tone='blue'] {{border-top-color:#468eff;}}
            QFrame#overviewCard[tone='teal'] {{background:{'#123b48' if self.dark else '#e8fbf8'};}}
            QFrame#overviewCard[tone='rose'] {{background:{'#382b43' if self.dark else '#fff0f4'};}}
            QFrame#overviewCard[tone='green'] {{background:{'#163b38' if self.dark else '#eafaf1'};}}
            QFrame#overviewCard[tone='orange'] {{background:{'#3c3430' if self.dark else '#fff4e9'};}}
            QFrame#overviewCard[tone='blue'] {{background:{'#183551' if self.dark else '#edf4ff'};}}
            QFrame#overviewCard QLabel {{background:transparent;}}
            QLabel#overviewCaption {{color:{muted};font-size:12px;font-weight:600;}}
            QLabel#overviewNote {{color:{muted};font-size:10px;}}
            QFrame#overviewCard[tone='teal'] QLabel#stat {{color:{'#43e0cf' if self.dark else '#008b80'};}}
            QFrame#overviewCard[tone='rose'] QLabel#stat {{color:{'#ff97ae' if self.dark else '#c33156'};}}
            QFrame#overviewCard[tone='green'] QLabel#stat {{color:{'#65e4ad' if self.dark else '#078553'};}}
            QFrame#overviewCard[tone='orange'] QLabel#stat {{color:{'#ffbd80' if self.dark else '#b35c00'};}}
            QGroupBox#quickActions QPushButton {{background:{'#183c57' if self.dark else '#eaf6ff'};border:1px solid {'#32627e' if self.dark else '#c6e4f7'};color:{ink};}}
            QGroupBox#quickActions QPushButton:hover {{background:#008d9a;color:white;}}
            QLabel#dashboardFoot {{color:{muted};font-size:12px;}}
            QProgressBar {{border:0;border-radius:6px;background:{border};height:8px;}}
            QProgressBar::chunk {{background:#18c6b5;border-radius:6px;}}
        """)
        self.style().unpolish(self);self.style().polish(self)
        for chart in (self.category_chart, self.trend_chart, self.asset_chart):
            chart.setProperty('darkTheme', self.dark)
            chart.update()
        self._mark_active_nav()

    def _mark_active_nav(self):
        for page_index,b in self.nav_map.items():
            b.setStyleSheet('background:#008da5;color:#ffffff;font-weight:700;' if page_index==self.stack.currentIndex() else 'background:transparent;color:#f0f9ff;border:0;')

    def closeEvent(self, event):
        controller=getattr(self,'update_controller',None)
        if controller is not None and controller.request_close():
            event.ignore()
            return
        worker=getattr(self, '_logo_worker', None)
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            if not getattr(self, '_waiting_for_logos', False):
                self._waiting_for_logos=True
                worker.finished.connect(self.close)
            event.ignore()
            return
        self.db.close()
        super().closeEvent(event)


def main():
    # Capture a consistent snapshot BEFORE changing the schema.
    DB_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as source:
            old_version = source.execute('PRAGMA user_version').fetchone()[0]
            if old_version < 8:
                backup_name='ailefinans.before_v08_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db'
                with sqlite3.connect(DB_DIR / backup_name) as target:
                    source.backup(target)
    try:
        migrate()
    except Exception as exc:
        print('Veritabanı açılamadı / güncellenemedi:', exc, file=sys.stderr)
        raise
    app = QApplication(sys.argv)
    with open_db() as db:
        migrate_kmh(db)
        with db:
            db.execute('''CREATE TABLE IF NOT EXISTS card_catalog_links (card_id INTEGER PRIMARY KEY REFERENCES credit_cards(id) ON DELETE CASCADE, bank TEXT NOT NULL, card_model TEXT NOT NULL)''')
            columns={r[1] for r in db.execute('PRAGMA table_info(card_catalog_links)')}
            if 'payment_network' not in columns:
                db.execute("ALTER TABLE card_catalog_links ADD COLUMN payment_network TEXT NOT NULL DEFAULT ''")
            migrate_documents(db)
            migrate_record_state(db)
            migrate_recurring(db)
            db.execute('PRAGMA user_version=8')
    window = App()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    if '--smoke-test' in sys.argv:
        from packaging_smoke import run
        run()
    else:
        main()
