import sys
import sqlite3
from contextlib import closing
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
from reporting_core import monthly_trend, category_expenses


from PySide6.QtCore import QThread, Signal

def circular_mascot(path, size=60):
    """Show the transparent owl asset without drawing any white badge behind it."""
    source=QPixmap(str(path))
    if source.isNull():
        return QPixmap()
    return source.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)

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
            # Explicit empty-state guidance, readable in both themes.
            text_color=QColor('#c6d8e5' if dark else '#446078')
            sub_color=QColor('#9eb8ca' if dark else '#738b9e')
            center_x=self.width()/2
            top=max(60,self.height()/2-45)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor('#20435a' if dark else '#e5f1f7'))
            p.drawEllipse(QRectF(center_x-22,top,44,44))
            p.setPen(QPen(QColor('#5bd5c4' if dark else '#198fa2'),2))
            p.drawLine(int(center_x-11),int(top+28),int(center_x-3),int(top+20))
            p.drawLine(int(center_x-3),int(top+20),int(center_x+4),int(top+25))
            p.drawLine(int(center_x+4),int(top+25),int(center_x+12),int(top+14))
            p.setPen(text_color)
            font.setPointSize(10);font.setBold(True);p.setFont(font)
            p.drawText(QRectF(15,top+51,self.width()-30,23),Qt.AlignmentFlag.AlignCenter,'Henüz görüntülenecek veri yok')
            p.setPen(sub_color);font.setPointSize(9);font.setBold(False);p.setFont(font)
            hint=('İlk gelir veya gider kaydınızla trend oluşur' if self.kind=='trend'
                  else 'Kayıt ekledikçe burada dağılımı göreceksiniz')
            p.drawText(QRectF(12,top+75,self.width()-24,30),Qt.AlignmentFlag.AlignCenter,hint)
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
        self.setWindowTitle('ParaNoya · Paranın peşini bırakma! · v1.2.5.8')
        icon_path=Path(__file__).parent/'assets'/'paranoya.ico'
        if not icon_path.is_file():
            icon_path=Path(__file__).parent/'assets'/'paranoya_mascot.png'
        self.setWindowIcon(QIcon(str(icon_path)))
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
        menu_scroll.verticalScrollBar().setStyleSheet('QScrollBar:vertical {background:#092d49;width:8px;margin:0;border:0;}'
            'QScrollBar::handle:vertical {background:#38718b;min-height:36px;border-radius:4px;}'
            'QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;border:0;}'
            'QScrollBar::up-arrow:vertical,QScrollBar::down-arrow:vertical {width:0;height:0;}'
            'QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:#092d49;}')
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
            ('GENEL', [(0, 'Genel Bakış')]),
            ('GÜNLÜK FİNANS', [(1, 'Banka Hesapları'), (2, 'Gelir / Gider'), (4, 'Transferler')]),
            ('BORÇLAR VE ÖDEMELER', [(5, 'Kredi Kartları'), (7, 'Ek Hesap / KMH'), (8, 'Aylık Ödemeler'), (10, 'Faturalar / Abonelikler')]),
            ('AİLE', [(3, 'Aile Paylaşımı'), (6, 'Ortak Gider Geçmişi')]),
            ('BELGELER VE DİĞER', [(9, 'Akıllı Belge Merkezi'), (11, 'Ürünler / Garantiler')]),
        ]
        self.nav_map = {}
        for group, entries in nav_groups:
            heading = QLabel(group)
            heading.setObjectName('navGroupHeading')
            menu_layout.addWidget(heading)
            for page_index, label in entries:
                btn = QPushButton(label)
                btn.setProperty('nav', True)
                btn.setProperty('active', False)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setToolTip(self.page_titles[page_index])
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
        # Keep the dashboard usable on smaller Windows displays; scroll vertically.
        self.dashboard.setMinimumWidth(600)
        dash=QVBoxLayout(self.dashboard)
        dash.setContentsMargins(12,8,12,14)
        dash.setSpacing(13)
        dashboard_intro=QLabel('Hesaplarınız, kart borçlarınız ve finans hareketleriniz tek ekranda.')
        dashboard_intro.setObjectName('dashboardSubtitle')
        dashboard_intro.setWordWrap(True)
        dash.addWidget(dashboard_intro)
        overview=QGridLayout();overview.setSpacing(12)
        self.balance_value=self.make_card(overview,0,'◈  Hesap Bakiyesi')
        self.debt_value=self.make_card(overview,1,'▣  Toplam Kart Borcu')
        self.income_value=self.make_card(overview,2,'↗  Toplam Gelir')
        self.expense_value=self.make_card(overview,3,'↘  Toplam Gider')
        self.remaining_value=self.make_card(overview,4,'◎  Gelir - Gider Farkı')
        for column in range(6):overview.setColumnStretch(column,1)
        dash.addLayout(overview)
        quick_box=QFrame()
        quick_box.setObjectName('quickActions')
        quick_area=QVBoxLayout(quick_box)
        quick_area.setContentsMargins(16,17,16,14)
        quick_area.setSpacing(8)
        quick_title=QLabel('Hızlı İşlemler')
        quick_title.setObjectName('quickActionsTitle')
        quick_title.setMinimumHeight(22)
        quick_area.addWidget(quick_title)
        quick=QHBoxLayout()
        quick.setSpacing(10)
        quick_area.addLayout(quick)
        for lbl,cb in [('＋  İşlem Ekle',self.create_transaction),('⇄  Transfer',self.create_transfer),('▧  Ekstre Yükle',self.import_document),('▣  Kart Ekle',self.new_card)]:
            b=QPushButton(lbl)
            b.setMinimumHeight(42)
            b.clicked.connect(cb)
            quick.addWidget(b,1)
        quick_box.setMinimumHeight(113)
        dash.addWidget(quick_box)
        middle=QGridLayout();middle.setSpacing(12)
        self.category_chart=FinanceBars('Giderlerin Kategori Dağılımı')
        self.trend_chart=FinanceBars('Aylık Gelir - Gider Trendi','trend')
        self.asset_chart=FinanceBars('Pozitif Hesap Bakiyeleri')
        middle.addWidget(self.trend_chart,0,0,1,2)
        middle.addWidget(self.category_chart,1,0)
        middle.addWidget(self.asset_chart,1,1)
        middle.setColumnStretch(0,1)
        middle.setColumnStretch(1,1)
        dash.addLayout(middle)
        bottom=QHBoxLayout();bottom.setSpacing(12)
        recent_box=QGroupBox('Son İşlemler');recent_layout=QVBoxLayout(recent_box)
        self.recent=self.make_table(['Tarih','Tür','Hesap','Kategori','Tutar']);recent_layout.addWidget(self.recent)
        self.recent.setMinimumHeight(220)
        bottom.addWidget(recent_box,3)
        due_box=QGroupBox('Yaklaşan Ödemeler');due_layout=QVBoxLayout(due_box)
        self.dashboard_due=self.make_table(['Vade','Kart / Hesap','Tutar'])
        self.dashboard_due.setMinimumHeight(220)
        due_layout.addWidget(self.dashboard_due);bottom.addWidget(due_box,2)
        dash.addLayout(bottom)
        dashboard_scroll=QScrollArea()
        dashboard_scroll.setObjectName('dashboardScroll')
        dashboard_scroll.setWidgetResizable(True)
        dashboard_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        dashboard_scroll.verticalScrollBar().setStyleSheet('QScrollBar:vertical {background:#e6f1f7;width:8px;margin:0;border:0;}'
            'QScrollBar::handle:vertical {background:#a0bacb;min-height:44px;border-radius:4px;}'
            'QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;border:0;}'
            'QScrollBar::up-arrow:vertical,QScrollBar::down-arrow:vertical {width:0;height:0;}'
            'QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:#e6f1f7;}')
        dashboard_scroll.setFrameShape(QFrame.Shape.NoFrame)
        dashboard_scroll.setWidget(self.dashboard)
        self.stack.addWidget(dashboard_scroll)
        accounts_page = QWidget()
        ac_layout = QVBoxLayout(accounts_page)
        ac_layout.setContentsMargins(18,16,18,18)
        ac_layout.setSpacing(14)
        account_header = QHBoxLayout()
        account_header.setSpacing(12)
        account_intro = QVBoxLayout()
        account_intro.setSpacing(3)
        account_title = QLabel('Hesaplarınız')
        account_title.setObjectName('sectionTitle')
        account_intro.addWidget(account_title)
        account_description = QLabel('Banka ve nakit hesaplarınızı, bakiyelerinizi ve bağlı ek hesap bilgilerinizi görüntüleyin.')
        account_description.setObjectName('sectionSubtitle')
        account_description.setWordWrap(True)
        account_intro.addWidget(account_description)
        account_header.addLayout(account_intro,1)
        new_acc = QPushButton('＋  Yeni Hesap')
        new_acc.setObjectName('accountPrimaryAction')
        new_acc.setMinimumHeight(43)
        new_acc.clicked.connect(self.create_account)
        account_header.addWidget(new_acc,0,Qt.AlignmentFlag.AlignTop)
        ac_layout.addLayout(account_header)

        account_metrics=QHBoxLayout()
        account_metrics.setSpacing(12)
        self.acc_total_count=QLabel('0')
        self.acc_total_balance=QLabel('0,00 ₺')
        self.acc_positive_balance=QLabel('0,00 ₺')
        for caption, value in [('TOPLAM HESAP',self.acc_total_count),
                               ('NET HESAP BAKİYESİ',self.acc_total_balance),
                               ('POZİTİF BAKİYELER',self.acc_positive_balance)]:
            tile=QFrame()
            tile.setObjectName('cardMetric')
            v=QVBoxLayout(tile)
            v.setContentsMargins(18,15,18,15)
            v.setSpacing(8)
            title=QLabel(caption)
            title.setObjectName('metricCaption')
            v.addWidget(title)
            value.setObjectName('metricNumber')
            v.addWidget(value)
            account_metrics.addWidget(tile,1)
        ac_layout.addLayout(account_metrics)

        account_list_title=QLabel('Hesap Listesi')
        account_list_title.setObjectName('sectionSubheading')
        ac_layout.addWidget(account_list_title)
        self.acc_table = self.make_table(['Hesap', 'Tür', 'Bakiye'])
        self.acc_table.setMinimumHeight(230)
        self.acc_table.setSortingEnabled(False)
        self._add_actions(ac_layout, self.acc_table, 'account')
        ac_layout.addWidget(self.acc_table,1)
        self.acc_empty_hint=QLabel('Henüz hesap eklenmedi. Başlamak için “Yeni Hesap” düğmesini kullanın.')
        self.acc_empty_hint.setObjectName('accountEmptyHint')
        self.acc_empty_hint.setWordWrap(True)
        ac_layout.addWidget(self.acc_empty_hint)

        self.account_details=QFrame()
        self.account_details.setObjectName('cardDetails')
        ad=QVBoxLayout(self.account_details)
        ad.setContentsMargins(18,15,18,16)
        ad.setSpacing(9)
        account_details_title=QLabel('SEÇİLİ HESAP')
        account_details_title.setObjectName('metricCaption')
        ad.addWidget(account_details_title)
        self.account_detail_heading=QLabel('Bir hesap seçerek ayrıntılarını görüntüleyin')
        self.account_detail_heading.setObjectName('cardDetailHeading')
        self.account_detail_body=QLabel('Hesap türü, bakiye ve bağlı KMH bilgileri burada görünür.')
        self.account_detail_body.setObjectName('accountDetailBody')
        self.account_detail_body.setWordWrap(True)
        self.account_logo=QLabel()
        self.account_logo.setFixedHeight(34)
        self.account_logo.hide()
        logo_row=QHBoxLayout()
        logo_row.setSpacing(12)
        logo_row.addWidget(self.account_logo)
        logo_row.addWidget(self.account_detail_heading, 1)
        ad.addLayout(logo_row)
        ad.addWidget(self.account_detail_body)
        ac_layout.addWidget(self.account_details)
        self.acc_table.itemSelectionChanged.connect(self.update_account_details)
        self.stack.addWidget(self._scroll_content_page(accounts_page,'accountsScroll',700))
        transactions_page = QWidget()
        tx_layout = QVBoxLayout(transactions_page)
        tx_layout.setContentsMargins(18,16,18,18)
        tx_layout.setSpacing(14)
        tx_header=QHBoxLayout()
        tx_intro=QVBoxLayout()
        tx_intro.setSpacing(3)
        tx_heading=QLabel('Gelir ve Giderleriniz')
        tx_heading.setObjectName('sectionTitle')
        tx_intro.addWidget(tx_heading)
        tx_description=QLabel('Hesap hareketlerini ve kredi kartı harcamalarını tek listede görüntüleyin.')
        tx_description.setObjectName('sectionSubtitle')
        tx_description.setWordWrap(True)
        tx_intro.addWidget(tx_description)
        tx_header.addLayout(tx_intro,1)
        new_tx = QPushButton('＋  Yeni Gelir / Gider')
        new_tx.setObjectName('accountPrimaryAction')
        new_tx.setMinimumHeight(43)
        new_tx.clicked.connect(self.create_transaction)
        tx_header.addWidget(new_tx,0,Qt.AlignmentFlag.AlignTop)
        tx_layout.addLayout(tx_header)

        tx_metrics=QHBoxLayout()
        tx_metrics.setSpacing(12)
        self.tx_income_total=QLabel('0,00 ₺')
        self.tx_expense_total=QLabel('0,00 ₺')
        self.tx_record_count=QLabel('0')
        for title,value in [('TOPLAM GELİR',self.tx_income_total),
                            ('TOPLAM GİDER',self.tx_expense_total),
                            ('İŞLEM SAYISI',self.tx_record_count)]:
            tile=QFrame()
            tile.setObjectName('cardMetric')
            inner=QVBoxLayout(tile)
            inner.setContentsMargins(18,15,18,15)
            inner.setSpacing(8)
            cap=QLabel(title)
            cap.setObjectName('metricCaption')
            inner.addWidget(cap)
            value.setObjectName('metricNumber')
            inner.addWidget(value)
            tx_metrics.addWidget(tile,1)
        tx_layout.addLayout(tx_metrics)

        tx_list_label=QLabel('İşlem Geçmişi')
        tx_list_label.setObjectName('sectionSubheading')
        tx_layout.addWidget(tx_list_label)
        tx_search_row=QHBoxLayout()
        self.tx_search_box=QLineEdit()
        self.tx_search_box.setObjectName('transactionSearch')
        self.tx_search_box.setPlaceholderText('Tarih, hesap, kategori veya açıklamada ara...')
        self.tx_search_box.setClearButtonEnabled(True)
        self.tx_search_box.textChanged.connect(self._filter_transactions)
        tx_search_row.addWidget(self.tx_search_box,1)
        tx_reset=QPushButton('Temizle')
        tx_reset.setObjectName('transactionClear')
        tx_reset.clicked.connect(self.tx_search_box.clear)
        tx_search_row.addWidget(tx_reset)
        tx_layout.addLayout(tx_search_row)

        self.tx_table = self.make_table(['Tarih', 'Tür', 'Hesap', 'Kategori', 'Açıklama', 'Tutar'])
        self.tx_table.setMinimumHeight(270)
        tx_layout.addWidget(self.tx_table,1)
        self.tx_filter_status=QLabel('')
        self.tx_filter_status.setObjectName('sectionSubtitle')
        tx_layout.addWidget(self.tx_filter_status)
        self.stack.addWidget(self._scroll_content_page(transactions_page,'transactionsScroll',620))
        family_page = QWidget()
        fam = QVBoxLayout(family_page)
        fam.setContentsMargins(18,16,18,18)
        fam.setSpacing(14)
        family_header=QHBoxLayout()
        family_intro=QVBoxLayout()
        family_intro.setSpacing(3)
        family_title=QLabel('Aile Paylaşımı')
        family_title.setObjectName('sectionTitle')
        family_intro.addWidget(family_title)
        family_note=QLabel('Aile üyeleri ve ortak gider paylarını aynı ekranda takip edin.')
        family_note.setObjectName('sectionSubtitle')
        family_note.setWordWrap(True)
        family_intro.addWidget(family_note)
        family_header.addLayout(family_intro,1)
        add_mem=QPushButton('＋  Aile Üyesi Ekle')
        add_mem.setObjectName('accountPrimaryAction')
        add_mem.setMinimumHeight(43)
        add_mem.clicked.connect(self.create_member)
        family_header.addWidget(add_mem,0,Qt.AlignmentFlag.AlignTop)
        fam.addLayout(family_header)
        family_actions=QFrame()
        family_actions.setObjectName('cardActionBar')
        family_actions_layout=QHBoxLayout(family_actions)
        family_actions_layout.setContentsMargins(12,10,12,10)
        shared_btn=QPushButton('＋  Ortak Gider Ekle ve Paylaştır')
        shared_btn.setMinimumHeight(42)
        shared_btn.clicked.connect(self.create_shared_expense)
        family_actions_layout.addWidget(shared_btn)
        family_actions_layout.addStretch()
        fam.addWidget(family_actions)
        family_list_title=QLabel('Aile Üyelerinin Gider Payları')
        family_list_title.setObjectName('sectionSubheading')
        fam.addWidget(family_list_title)
        self.members_table=self.make_table(['Aile üyesi','Gider payı'])
        self.members_table.setMinimumHeight(230)
        fam.addWidget(self.members_table,1)
        self.family_empty_hint=QLabel('Henüz aile üyesi bulunmuyor. Paylaşım için önce bir aile üyesi ekleyin.')
        self.family_empty_hint.setObjectName('accountEmptyHint')
        self.family_empty_hint.setWordWrap(True)
        fam.addWidget(self.family_empty_hint)
        self.stack.addWidget(self._scroll_content_page(family_page,'familyScroll',570))
        transfer_page = QWidget()
        tl=QVBoxLayout(transfer_page)
        tl.setContentsMargins(18,16,18,18)
        tl.setSpacing(14)
        transfer_header=QHBoxLayout()
        transfer_intro=QVBoxLayout()
        transfer_intro.setSpacing(3)
        transfer_title=QLabel('Hesaplar Arası Transferler')
        transfer_title.setObjectName('sectionTitle')
        transfer_intro.addWidget(transfer_title)
        transfer_desc=QLabel('Hesaplarınız arasındaki para aktarım geçmişini görüntüleyin.')
        transfer_desc.setObjectName('sectionSubtitle')
        transfer_desc.setWordWrap(True)
        transfer_intro.addWidget(transfer_desc)
        transfer_header.addLayout(transfer_intro,1)
        transfer_btn=QPushButton('＋  Yeni Transfer')
        transfer_btn.setObjectName('accountPrimaryAction')
        transfer_btn.setMinimumHeight(43)
        transfer_btn.clicked.connect(self.create_transfer)
        transfer_header.addWidget(transfer_btn,0,Qt.AlignmentFlag.AlignTop)
        tl.addLayout(transfer_header)
        transfer_list_label=QLabel('Transfer Geçmişi')
        transfer_list_label.setObjectName('sectionSubheading')
        tl.addWidget(transfer_list_label)
        self.transfers_table=self.make_table(['Tarih','Gönderen','Alıcı','Tutar','Açıklama'])
        self.transfers_table.setMinimumHeight(280)
        tl.addWidget(self.transfers_table,1)
        self.transfers_empty_hint=QLabel('Henüz transfer kaydı yok. Yeni bir transfer ekleyebilirsiniz.')
        self.transfers_empty_hint.setObjectName('accountEmptyHint')
        self.transfers_empty_hint.setWordWrap(True)
        tl.addWidget(self.transfers_empty_hint)
        self.stack.addWidget(self._scroll_content_page(transfer_page,'transferScroll',530))
        cardpage=QWidget()
        cl=QVBoxLayout(cardpage)
        cl.setContentsMargins(18,16,18,18)
        cl.setSpacing(14)
        card_header=QHBoxLayout()
        card_header.setSpacing(12)
        card_intro=QVBoxLayout()
        card_intro.setSpacing(3)
        card_title=QLabel('Kredi Kartlarınız')
        card_title.setObjectName('sectionTitle')
        card_intro.addWidget(card_title)
        card_description=QLabel('Kart limitlerinizi, kalan borçlarınızı ve yaklaşan taksitleri izleyin.')
        card_description.setObjectName('sectionSubtitle')
        card_description.setWordWrap(True)
        card_intro.addWidget(card_description)
        card_header.addLayout(card_intro,1)
        new_card_button=QPushButton('＋  Kart Ekle')
        new_card_button.setObjectName('accountPrimaryAction')
        new_card_button.setMinimumHeight(43)
        new_card_button.clicked.connect(self.new_card)
        card_header.addWidget(new_card_button,0,Qt.AlignmentFlag.AlignTop)
        cl.addLayout(card_header)

        card_metrics=QHBoxLayout()
        card_metrics.setSpacing(12)
        self.card_total_label=QLabel('0,00 ₺')
        self.card_limit_label=QLabel('0,00 ₺')
        self.card_available_label=QLabel('0,00 ₺')
        for title,widget in [('TOPLAM KART BORCU',self.card_total_label),
                             ('TOPLAM KART LİMİTİ',self.card_limit_label),
                             ('TAHMİNİ KULLANILABİLİR',self.card_available_label)]:
            tile=QFrame()
            tile.setObjectName('cardMetric')
            v=QVBoxLayout(tile)
            v.setContentsMargins(18,15,18,15)
            v.setSpacing(8)
            cap=QLabel(title)
            cap.setObjectName('metricCaption')
            v.addWidget(cap)
            widget.setObjectName('metricNumber')
            v.addWidget(widget)
            card_metrics.addWidget(tile,1)
        cl.addLayout(card_metrics)

        card_action_bar=QFrame()
        card_action_bar.setObjectName('cardActionBar')
        card_actions=QHBoxLayout(card_action_bar)
        card_actions.setContentsMargins(12,10,12,10)
        card_actions.setSpacing(10)
        for label,callback in [('＋  Taksitli Alışveriş',self.new_purchase),
                               ('₺  Kart Borcu Öde',self.new_card_payment)]:
            button=QPushButton(label)
            button.setMinimumHeight(42)
            button.clicked.connect(callback)
            card_actions.addWidget(button)
        card_actions.addStretch()
        cl.addWidget(card_action_bar)

        cards_heading=QLabel('Kartlarım')
        cards_heading.setObjectName('sectionSubheading')
        cl.addWidget(cards_heading)
        self.card_table=self.make_table(['Kart','Kesim','Ödeme günü','Limit','Kalan borç'])
        self.card_table.setMinimumHeight(220)
        self._add_actions(cl,self.card_table,'card')
        cl.addWidget(self.card_table,1)
        self.cards_empty_hint=QLabel('Henüz kredi kartı eklenmedi. Başlamak için “Kart Ekle” düğmesini kullanın.')
        self.cards_empty_hint.setObjectName('accountEmptyHint')
        self.cards_empty_hint.setWordWrap(True)
        cl.addWidget(self.cards_empty_hint)

        self.card_details=QFrame()
        self.card_details.setObjectName('cardDetails')
        detail_layout=QVBoxLayout(self.card_details)
        detail_layout.setContentsMargins(18,15,18,16)
        detail_layout.setSpacing(9)
        card_detail_caption=QLabel('SEÇİLİ KART')
        card_detail_caption.setObjectName('metricCaption')
        detail_layout.addWidget(card_detail_caption)
        self.card_detail_heading=QLabel('Kart seçildiğinde ayrıntıları burada görünecek')
        self.card_detail_heading.setObjectName('cardDetailHeading')
        self.card_detail_body=QLabel('Banka, kart modeli, ödeme ağı, limit ve borç bilgileri')
        self.card_detail_body.setObjectName('accountDetailBody')
        self.card_detail_body.setWordWrap(True)
        self.card_logo=QLabel()
        self.card_logo.setFixedHeight(34)
        self.card_logo.hide()
        logo_row=QHBoxLayout()
        logo_row.setSpacing(12)
        logo_row.addWidget(self.card_logo)
        logo_row.addWidget(self.card_detail_heading,1)
        detail_layout.addLayout(logo_row)
        detail_layout.addWidget(self.card_detail_body)
        cl.addWidget(self.card_details)

        due_heading=QLabel('Yaklaşan Taksitler · Tahmini Vadeler')
        due_heading.setObjectName('sectionSubheading')
        cl.addWidget(due_heading)
        self.due_table=self.make_table(['Kart','Vade','Ödenmemiş tutar','Kategori','Açıklama'])
        self.due_table.setMinimumHeight(175)
        cl.addWidget(self.due_table,1)
        self.stack.addWidget(self._scroll_content_page(cardpage,'cardsScroll',940))
        historypage=QWidget()
        hl=QVBoxLayout(historypage)
        hl.setContentsMargins(18,16,18,18)
        hl.setSpacing(14)
        shared_header=QHBoxLayout()
        shared_intro=QVBoxLayout()
        shared_intro.setSpacing(3)
        shared_title=QLabel('Ortak Gider Geçmişi')
        shared_title.setObjectName('sectionTitle')
        shared_intro.addWidget(shared_title)
        shared_description=QLabel('Aile ortak giderlerini ve üyelerin paylarını inceleyin.')
        shared_description.setObjectName('sectionSubtitle')
        shared_description.setWordWrap(True)
        shared_intro.addWidget(shared_description)
        shared_header.addLayout(shared_intro,1)
        correct=QPushButton('Payları Düzelt')
        correct.setObjectName('accountPrimaryAction')
        correct.setMinimumHeight(43)
        correct.clicked.connect(self.correct_split)
        shared_header.addWidget(correct,0,Qt.AlignmentFlag.AlignTop)
        hl.addLayout(shared_header)
        shared_heading=QLabel('Paylaştırılmış Giderler')
        shared_heading.setObjectName('sectionSubheading')
        hl.addWidget(shared_heading)
        self.shared_table=self.make_table(['ID','Tarih','Ödeyen hesap','Kategori','Gider','Üye payları'])
        self.shared_table.setMinimumHeight(260)
        hl.addWidget(self.shared_table,1)
        self.shared_empty_hint=QLabel('Henüz ortak gider kaydı bulunmuyor. Aile Paylaşımı bölümünden ortak gider ekleyebilirsiniz.')
        self.shared_empty_hint.setObjectName('accountEmptyHint')
        self.shared_empty_hint.setWordWrap(True)
        hl.addWidget(self.shared_empty_hint)
        shared_info=QLabel('Pay düzeltmesi toplam gider tutarını değiştirmez.')
        shared_info.setObjectName('sectionSubtitle')
        hl.addWidget(shared_info)
        self.stack.addWidget(self._scroll_content_page(historypage,'sharedHistoryScroll',530))
        kmhpage=QWidget()
        kl=QVBoxLayout(kmhpage)
        kl.setContentsMargins(18,16,18,18)
        kl.setSpacing(14)
        kmh_header=QHBoxLayout()
        kmh_intro=QVBoxLayout()
        kmh_intro.setSpacing(3)
        kmh_title=QLabel('Ek Hesap / KMH')
        kmh_title.setObjectName('sectionTitle')
        kmh_intro.addWidget(kmh_title)
        kmh_description=QLabel('Ek hesap limitlerinizi, kullanımlarınızı ve taksitli KMH borçlarınızı takip edin.')
        kmh_description.setObjectName('sectionSubtitle')
        kmh_description.setWordWrap(True)
        kmh_intro.addWidget(kmh_description)
        kmh_header.addLayout(kmh_intro,1)
        kmh_create=QPushButton('＋  Ek Limit Tanımla')
        kmh_create.setObjectName('accountPrimaryAction')
        kmh_create.setMinimumHeight(43)
        kmh_create.clicked.connect(self.new_overdraft)
        kmh_header.addWidget(kmh_create,0,Qt.AlignmentFlag.AlignTop)
        kl.addLayout(kmh_header)
        kmh_metrics=QHBoxLayout()
        kmh_metrics.setSpacing(12)
        self.kmh_limit_total=QLabel('0,00 ₺')
        self.kmh_used_total=QLabel('0,00 ₺')
        self.kmh_available_total=QLabel('0,00 ₺')
        for caption,value in [('TOPLAM KMH LİMİTİ',self.kmh_limit_total),
                              ('KULLANILAN KMH',self.kmh_used_total),
                              ('KALAN KMH LİMİTİ',self.kmh_available_total)]:
            tile=QFrame()
            tile.setObjectName('cardMetric')
            v=QVBoxLayout(tile)
            v.setContentsMargins(18,15,18,15)
            v.setSpacing(8)
            label=QLabel(caption)
            label.setObjectName('metricCaption')
            v.addWidget(label)
            value.setObjectName('metricNumber')
            v.addWidget(value)
            kmh_metrics.addWidget(tile,1)
        kl.addLayout(kmh_metrics)
        kmh_action_bar=QFrame()
        kmh_action_bar.setObjectName('cardActionBar')
        ka=QHBoxLayout(kmh_action_bar)
        ka.setContentsMargins(12,10,12,10)
        ka.setSpacing(10)
        for label,fn in [('₺  KMH Kullan / Kapat',self.kmh_draw_repay),
                         ('＋  Taksitli KMH Borcu',self.new_kmh_loan)]:
            button=QPushButton(label)
            button.setMinimumHeight(42)
            button.clicked.connect(fn)
            ka.addWidget(button)
        ka.addStretch()
        kl.addWidget(kmh_action_bar)
        kmh_list_heading=QLabel('Ek Hesaplarım')
        kmh_list_heading.setObjectName('sectionSubheading')
        kl.addWidget(kmh_list_heading)
        self.kmh_table=self.make_table(['Banka hesabı','KMH limiti','Kullanılan','Kalan limit'])
        self.kmh_table.setMinimumHeight(220)
        self._add_actions(kl,self.kmh_table,'kmh')
        kl.addWidget(self.kmh_table,1)
        self.kmh_empty_hint=QLabel('Henüz ek hesap tanımlanmadı. Banka hesabınıza ek limit ekleyebilirsiniz.')
        self.kmh_empty_hint.setObjectName('accountEmptyHint')
        self.kmh_empty_hint.setWordWrap(True)
        kl.addWidget(self.kmh_empty_hint)
        self.kmh_details=QFrame()
        self.kmh_details.setObjectName('cardDetails')
        kd=QVBoxLayout(self.kmh_details)
        kd.setContentsMargins(18,15,18,16)
        kd.setSpacing(9)
        kmh_detail_caption=QLabel('SEÇİLİ EK HESAP')
        kmh_detail_caption.setObjectName('metricCaption')
        kd.addWidget(kmh_detail_caption)
        self.kmh_detail_heading=QLabel('Bir KMH hesabı seçin')
        self.kmh_detail_heading.setObjectName('cardDetailHeading')
        self.kmh_detail_body=QLabel('Kullanım, kalan limit ve bağlı taksitli borçların özeti burada görünür.')
        self.kmh_detail_body.setObjectName('accountDetailBody')
        self.kmh_detail_body.setWordWrap(True)
        self.kmh_logo=QLabel()
        self.kmh_logo.setFixedHeight(34)
        self.kmh_logo.hide()
        logo_row=QHBoxLayout()
        logo_row.setSpacing(12)
        logo_row.addWidget(self.kmh_logo)
        logo_row.addWidget(self.kmh_detail_heading,1)
        kd.addLayout(logo_row)
        kd.addWidget(self.kmh_detail_body)
        kl.addWidget(self.kmh_details)
        self.kmh_table.itemSelectionChanged.connect(self.update_kmh_details)
        kmh_note=QLabel('Taksitli KMH planları, normal ek hesap kullanımından ayrı borç olarak izlenir.')
        kmh_note.setObjectName('sectionSubtitle')
        kmh_note.setWordWrap(True)
        kl.addWidget(kmh_note)
        self.stack.addWidget(self._scroll_content_page(kmhpage,'overdraftScroll',880))
        calpage=QWidget()
        cal=QVBoxLayout(calpage)
        cal.setContentsMargins(18,16,18,18)
        cal.setSpacing(14)
        calendar_header=QHBoxLayout()
        calendar_intro=QVBoxLayout()
        calendar_intro.setSpacing(3)
        calendar_title=QLabel('Aylık Ödeme Takvimi')
        calendar_title.setObjectName('sectionTitle')
        calendar_intro.addWidget(calendar_title)
        calendar_desc=QLabel('KMH taksitlerini, gecikmeleri ve yaklaşan faturaları bir arada izleyin.')
        calendar_desc.setObjectName('sectionSubtitle')
        calendar_desc.setWordWrap(True)
        calendar_intro.addWidget(calendar_desc)
        calendar_header.addLayout(calendar_intro,1)
        pay_calendar_button=QPushButton('₺  Seçili KMH Taksidini Öde')
        pay_calendar_button.setObjectName('accountPrimaryAction')
        pay_calendar_button.setMinimumHeight(43)
        pay_calendar_button.clicked.connect(self.kmh_pay)
        calendar_header.addWidget(pay_calendar_button,0,Qt.AlignmentFlag.AlignTop)
        cal.addLayout(calendar_header)

        calendar_metrics=QHBoxLayout()
        calendar_metrics.setSpacing(12)
        self.calendar_month_label=QLabel('0,00 ₺')
        self.calendar_overdue_label=QLabel('0,00 ₺')
        self.calendar_total_label=QLabel('0,00 ₺')
        for caption,value in [('BU AY ÖDENECEK',self.calendar_month_label),
                              ('GECİKEN',self.calendar_overdue_label),
                              ('TOPLAM BEKLEYEN',self.calendar_total_label)]:
            tile=QFrame()
            tile.setObjectName('cardMetric')
            v=QVBoxLayout(tile)
            v.setContentsMargins(18,15,18,15)
            v.setSpacing(8)
            label=QLabel(caption)
            label.setObjectName('metricCaption')
            v.addWidget(label)
            value.setObjectName('metricNumber')
            v.addWidget(value)
            calendar_metrics.addWidget(tile,1)
        cal.addLayout(calendar_metrics)

        calendar_list_heading=QLabel('KMH Taksit Takvimi')
        calendar_list_heading.setObjectName('sectionSubheading')
        cal.addWidget(calendar_list_heading)
        filter_bar=QHBoxLayout()
        filter_label=QLabel('Gösterilecek kayıtlar')
        filter_label.setObjectName('sectionSubtitle')
        filter_bar.addWidget(filter_label)
        self.calendar_filter=QComboBox()
        for label,code in [('Tüm bekleyenler','all'),('Bu ay','this_month'),
                           ('Gecikenler','overdue'),('Gelecek ödemeler','future')]:
            self.calendar_filter.addItem(label,code)
        self.calendar_filter.setMinimumWidth(190)
        self.calendar_filter.currentIndexChanged.connect(self.refresh_calendar)
        filter_bar.addWidget(self.calendar_filter)
        filter_bar.addStretch()
        cal.addLayout(filter_bar)
        self.calendar_table=self.make_table(['ID','Banka','Vade','Ödenecek','Durum','Açıklama'])
        self.calendar_table.setMinimumHeight(180)
        cal.addWidget(self.calendar_table,1)
        self.calendar_empty_hint=QLabel('Bu filtreye uygun bekleyen KMH taksidi bulunmuyor.')
        self.calendar_empty_hint.setObjectName('accountEmptyHint')
        self.calendar_empty_hint.setWordWrap(True)
        cal.addWidget(self.calendar_empty_hint)

        recurring_heading=QLabel('Faturalar ve Abonelikler')
        recurring_heading.setObjectName('sectionSubheading')
        cal.addWidget(recurring_heading)
        recurring_note=QLabel('Yenilemeler ödeme onaylanmadan gider olarak kaydedilmez.')
        recurring_note.setObjectName('sectionSubtitle')
        recurring_note.setWordWrap(True)
        cal.addWidget(recurring_note)
        self.calendar_recurring=self.make_table(['Ad','Tür','Vade','Tutar','Durum'])
        self.calendar_recurring.setMinimumHeight(165)
        cal.addWidget(self.calendar_recurring,1)
        self.calendar_recurring_empty_hint=QLabel('Yaklaşan fatura veya abonelik bulunmuyor.')
        self.calendar_recurring_empty_hint.setObjectName('accountEmptyHint')
        self.calendar_recurring_empty_hint.setWordWrap(True)
        cal.addWidget(self.calendar_recurring_empty_hint)
        self.stack.addWidget(self._scroll_content_page(calpage,'paymentsScroll',860))
        documents_page=QWidget()
        dv=QVBoxLayout(documents_page)
        dv.setContentsMargins(18,16,18,18)
        dv.setSpacing(14)
        doc_header=QHBoxLayout()
        doc_intro=QVBoxLayout()
        doc_intro.setSpacing(3)
        doc_title=QLabel('Akıllı Belge Merkezi')
        doc_title.setObjectName('sectionTitle')
        doc_intro.addWidget(doc_title)
        doc_description=QLabel('Bordro, fatura ve ekstreleri önce inceleyin; finans kaydı için ayrıca onay verin.')
        doc_description.setObjectName('sectionSubtitle')
        doc_description.setWordWrap(True)
        doc_intro.addWidget(doc_description)
        doc_header.addLayout(doc_intro,1)
        upload=QPushButton('＋  Belge Yükle')
        upload.setObjectName('accountPrimaryAction')
        upload.setMinimumHeight(43)
        upload.setToolTip('Desteklenen dosyalar: PDF, CSV, Excel ve TXT')
        upload.clicked.connect(self.import_document)
        doc_header.addWidget(upload,0,Qt.AlignmentFlag.AlignTop)
        dv.addLayout(doc_header)

        backup_tools=QFrame()
        backup_tools.setObjectName('cardActionBar')
        backup_bar=QHBoxLayout(backup_tools)
        backup_bar.setContentsMargins(12,10,12,10)
        backup_bar.setSpacing(10)
        backup_title=QLabel('Veri Güvenliği')
        backup_title.setObjectName('sectionSubheading')
        backup_bar.addWidget(backup_title)
        backup_bar.addStretch()
        for title,callback in [('Yedek Oluştur',self.create_backup),
                               ('Yedekten Geri Yükle',self.restore_from_backup)]:
            button=QPushButton(title)
            button.setMinimumHeight(40)
            button.clicked.connect(callback)
            backup_bar.addWidget(button)
        dv.addWidget(backup_tools)

        documents_heading=QLabel('Yüklenen Belgeler')
        documents_heading.setObjectName('sectionSubheading')
        dv.addWidget(documents_heading)
        self.doc_table=self.make_table(['ID','Dosya','Tür','Durum','Tarih'])
        self.doc_table.setMinimumHeight(185)
        dv.addWidget(self.doc_table,1)
        self.doc_empty_hint=QLabel('Henüz belge yüklenmedi. İncelemek istediğiniz belgeyi ekleyebilirsiniz.')
        self.doc_empty_hint.setObjectName('accountEmptyHint')
        self.doc_empty_hint.setWordWrap(True)
        dv.addWidget(self.doc_empty_hint)

        preview_heading=QLabel('Belge Önizleme')
        preview_heading.setObjectName('sectionSubheading')
        dv.addWidget(preview_heading)
        preview_actions=QHBoxLayout()
        preview_button=QPushButton('Seçili Belgenin Satırlarını Göster')
        preview_button.setMinimumHeight(40)
        preview_button.clicked.connect(self.preview_document_rows)
        preview_actions.addWidget(preview_button)
        preview_actions.addStretch()
        dv.addLayout(preview_actions)
        self.doc_preview=self.make_table(['Satır','Tarih','Açıklama / Taksit','Tutar','Durum'])
        self.doc_preview.setMinimumHeight(165)
        dv.addWidget(self.doc_preview,1)
        doc_warning=QLabel('Önizleme finans kaydı oluşturmaz. Tutar ve tarihleri orijinal banka belgesiyle karşılaştırın.')
        doc_warning.setObjectName('documentSafetyNote')
        doc_warning.setWordWrap(True)
        dv.addWidget(doc_warning)

        post_actions=QHBoxLayout()
        post_actions.addStretch()
        salary=QPushButton('Seçili Belgeden Gelir / Gider Oluştur')
        salary.setObjectName('accountPrimaryAction')
        salary.setMinimumHeight(43)
        salary.clicked.connect(self.post_document_entry)
        post_actions.addWidget(salary)
        dv.addLayout(post_actions)
        self.stack.addWidget(self._scroll_content_page(documents_page,'documentsScroll',940))
        # Düzenli fatura ve abonelik modülü: tüm seçimler içerik alanındadır.
        recurring_page=QWidget()
        recurring_layout=QVBoxLayout(recurring_page)
        recurring_layout.setContentsMargins(18,16,18,18)
        recurring_layout.setSpacing(14)
        # Keep form rows at their natural height; the outer viewport scrolls instead of squeezing them.
        recurring_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
        # A real minimum content height forces scrolling at 920x600 instead of compressed rows.
        recurring_page.setMinimumHeight(930)
        recurring_title=QLabel('Faturalar ve Abonelikler')
        recurring_title.setObjectName('sectionTitle')
        recurring_layout.addWidget(recurring_title)
        recurring_description=QLabel('Düzenli ödemeleri planlayın. Finans kaydı yalnızca ödeme onaylandığında oluşturulur.')
        recurring_description.setObjectName('sectionSubtitle')
        recurring_description.setWordWrap(True)
        recurring_layout.addWidget(recurring_description)

        entry=QGroupBox('Yeni Düzenli Ödeme')
        entry_form=QFormLayout(entry)
        entry_form.setSpacing(10)
        entry_form.setContentsMargins(16,20,16,16)
        entry_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        entry_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.rec_name=QLineEdit()
        self.rec_name.setPlaceholderText('İnternet, elektrik, yazılım aboneliği...')
        self.rec_kind=QComboBox()
        self.rec_kind.addItem('Fatura','bill')
        self.rec_kind.addItem('Abonelik','subscription')
        self.rec_category=QLineEdit('Faturalar')
        self.rec_amount=QDoubleSpinBox()
        self.rec_amount.setRange(.01,99999999)
        self.rec_amount.setDecimals(2)
        self.rec_amount.setSuffix(' TL')
        self.rec_freq=QComboBox()
        for label,value in [('Aylık','monthly'),('3 ayda bir','quarterly'),('Yıllık','yearly')]:
            self.rec_freq.addItem(label,value)
        self.rec_due=QDateEdit()
        self.rec_due.setCalendarPopup(True)
        self.rec_due.setDate(QDate.currentDate())
        self.rec_due.setDisplayFormat('dd.MM.yyyy')
        for label,widget in [('Ad',self.rec_name),('Tür',self.rec_kind),
                             ('Kategori',self.rec_category),('Tutar',self.rec_amount),
                             ('Yenileme sıklığı',self.rec_freq),('İlk vade',self.rec_due)]:
            widget.setMinimumHeight(42)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            entry_form.addRow(label,widget)
        save_rec=QPushButton('＋  Düzenli Ödeme Ekle')
        save_rec.setObjectName('accountPrimaryAction')
        save_rec.setMinimumHeight(43)
        save_rec.clicked.connect(self.save_recurring)
        entry_form.addRow(save_rec)
        entry.setMinimumHeight(425)
        entry.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed)
        recurring_layout.addWidget(entry)

        recurring_list_title=QLabel('Gecikmiş ve Yaklaşan Ödemeler')
        recurring_list_title.setObjectName('sectionSubheading')
        recurring_layout.addWidget(recurring_list_title)
        self.rec_table=self.make_table(['ID','Ad','Tür','Vade','Tutar','Kategori','Durum'])
        self.rec_table.setMinimumHeight(195)
        self.rec_table.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Minimum)
        recurring_layout.addWidget(self.rec_table)
        self.rec_empty_hint=QLabel('Henüz planlanmış fatura veya abonelik yok.')
        self.rec_empty_hint.setObjectName('accountEmptyHint')
        self.rec_empty_hint.setWordWrap(True)
        recurring_layout.addWidget(self.rec_empty_hint)
        rec_actions=QFrame()
        rec_actions.setObjectName('cardActionBar')
        rec_buttons=QHBoxLayout(rec_actions)
        rec_buttons.setContentsMargins(12,10,12,10)
        rec_buttons.setSpacing(10)
        rec_pay=QPushButton('₺  Seçili Dönemi Öde')
        rec_pay.setMinimumHeight(42)
        rec_pay.clicked.connect(self.pay_recurring)
        rec_pause=QPushButton('Seçili Ödemeyi Durdur')
        rec_pause.setMinimumHeight(42)
        rec_pause.clicked.connect(self.pause_recurring)
        rec_buttons.addWidget(rec_pay)
        rec_buttons.addWidget(rec_pause)
        rec_buttons.addStretch()
        recurring_layout.addWidget(rec_actions)
        recurring_scroll=QScrollArea()
        recurring_scroll.setObjectName('recurringScroll')
        recurring_scroll.setWidgetResizable(True)
        recurring_scroll.setFrameShape(QFrame.Shape.NoFrame)
        recurring_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        recurring_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        recurring_scroll.setWidget(recurring_page)
        self.stack.addWidget(recurring_scroll)
        products_page=QWidget()
        pv=QVBoxLayout(products_page)
        pv.setContentsMargins(18,16,18,18)
        pv.setSpacing(14)
        products_header=QHBoxLayout()
        products_intro=QVBoxLayout()
        products_intro.setSpacing(3)
        products_title=QLabel('Ürünler ve Garantiler')
        products_title.setObjectName('sectionTitle')
        products_intro.addWidget(products_title)
        products_desc=QLabel('Satın aldığınız ürünlerin garanti, servis ve belgelerini yönetin. Finans hareketi otomatik oluşmaz.')
        products_desc.setObjectName('sectionSubtitle')
        products_desc.setWordWrap(True)
        products_intro.addWidget(products_desc)
        products_header.addLayout(products_intro,1)
        add_product=QPushButton('＋  Ürün Ekle')
        add_product.setObjectName('accountPrimaryAction')
        add_product.setMinimumHeight(43)
        add_product.clicked.connect(self.new_product)
        products_header.addWidget(add_product,0,Qt.AlignmentFlag.AlignTop)
        pv.addLayout(products_header)

        product_tools=QFrame()
        product_tools.setObjectName('cardActionBar')
        product_tool_layout=QVBoxLayout(product_tools)
        product_tool_layout.setContentsMargins(12,10,12,10)
        product_tool_layout.setSpacing(8)
        product_main_actions=QHBoxLayout()
        product_main_actions.setSpacing(8)
        for title,callback in [('＋  Servis Kaydı',self.new_service),
                               ('＋  Belge Bağla',self.new_product_document),
                               ('Belgeleri Görüntüle',self.show_product_documents)]:
            button=QPushButton(title)
            button.setMinimumHeight(40)
            button.clicked.connect(callback)
            product_main_actions.addWidget(button)
        product_main_actions.addStretch()
        product_tool_layout.addLayout(product_main_actions)
        product_record_actions=QHBoxLayout()
        product_record_actions.setSpacing(8)
        for title,callback in [('Arşivle',lambda:self.product_state('archived')),
                               ('Geri Yükle',lambda:self.product_state('active'))]:
            button=QPushButton(title)
            button.clicked.connect(callback)
            product_record_actions.addWidget(button)
        product_record_actions.addStretch()
        product_tool_layout.addLayout(product_record_actions)
        pv.addWidget(product_tools)

        product_list_header=QHBoxLayout()
        product_list_title=QLabel('Kayıtlı Ürünler')
        product_list_title.setObjectName('sectionSubheading')
        product_list_header.addWidget(product_list_title)
        product_list_header.addStretch()
        self.product_show_archived=QCheckBox('Arşivlenenleri de göster')
        self.product_show_archived.stateChanged.connect(self.refresh_products)
        product_list_header.addWidget(self.product_show_archived)
        pv.addLayout(product_list_header)
        self.products_table=self.make_table(['Ad','Marka','Model','Satın alma','Fiyat','Garanti bitişi','Durum'])
        self.products_table.setMinimumHeight(250)
        pv.addWidget(self.products_table,1)
        self.products_empty_hint=QLabel('Henüz ürün bulunmuyor. İlk ürününüzü ekleyerek garanti takibine başlayabilirsiniz.')
        self.products_empty_hint.setObjectName('accountEmptyHint')
        self.products_empty_hint.setWordWrap(True)
        pv.addWidget(self.products_empty_hint)
        self.products_note=QLabel('')
        self.products_note.setObjectName('sectionSubtitle')
        pv.addWidget(self.products_note)
        self.stack.addWidget(self._scroll_content_page(products_page,'productsScroll',700))

        self.dashboard_info=QLabel('');self.dashboard_info.setObjectName('dashboardFoot');dash.addWidget(self.dashboard_info)
        content.addWidget(self.stack, 1)
        outer.addLayout(content, 1)
        self.select_page(0)
        self.apply_theme()
        # Arayüz hazır olduğunda eksik logoları asenkron indir.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(250, self.download_bank_logos)

    @staticmethod
    def _scroll_content_page(page, object_name, minimum_height):
        """Preserve form controls at small window sizes by scrolling the content."""
        layout=page.layout()
        if layout is not None:
            # SetMinimumSize recalculates and overwrites an explicit widget height.
            # Keep natural layout behavior; the viewport scrolls instead.
            layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetDefaultConstraint)
        page.setMinimumHeight(minimum_height)
        scroll=QScrollArea()
        scroll.setObjectName(object_name)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

    def global_search(self):
        term=self.search_box.text().strip()
        if not term:
            return
        self.select_page(2)
        self.tx_search_box.setText(term)
        self.tx_search_box.setFocus()

    def _filter_transactions(self, *_):
        """Filter the visible view, never change stored financial records."""
        if not hasattr(self,'tx_table'):
            return
        term=self.tx_search_box.text().strip().casefold()
        count=0
        for row in range(self.tx_table.rowCount()):
            hit=not term or any(
                term in (self.tx_table.item(row,column).text() if self.tx_table.item(row,column) else '').casefold()
                for column in range(self.tx_table.columnCount())
            )
            self.tx_table.setRowHidden(row,not hit)
            count+=hit
        total=self.tx_table.rowCount()
        self.tx_filter_status.setText(
            f'{count} / {total} işlem gösteriliyor' if term else f'{total} işlem listeleniyor'
        )

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
        # Three equal cards above two wider cards; no unused right-hand gap.
        if col < 3:
            grid.addWidget(box,0,col*2,1,2)
        else:
            grid.addWidget(box,1,(col-3)*3,1,3)
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
        self.products_empty_hint.setVisible(not bool(rows))

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
        # The modern content pages already have their own heading; don't show it twice.
        self.heading.setVisible(index==0)
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
        self.acc_empty_hint.setVisible(not bool(accs))
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
        self.tx_income_total.setText(money(sum(amt for _,kind,_,_,_,amt in rows if kind=='income')))
        self.tx_expense_total.setText(money(sum(amt for _,kind,_,_,_,amt in rows if kind!='income')))
        self.tx_record_count.setText(str(len(rows)))
        self._filter_transactions()
        self.fill_table(self.recent, [(when, typ, acct, cat, amt)
                                      for when, typ, acct, cat, note, amt in shown[:10]])
        family_rows=member_expenses(self.db)
        self.fill_table(self.members_table, [(name,money(cents)) for name,cents in family_rows])
        self.family_empty_hint.setVisible(not bool(family_rows))
        transfer_rows = self.db.execute("""SELECT tr.recorded_at, a.name,b.name,tr.amount_cents,tr.note
            FROM transfers tr JOIN accounts a ON a.id=tr.from_account_id
            JOIN accounts b ON b.id=tr.to_account_id
            WHERE tr.profile_id=? ORDER BY tr.id DESC""",(pid,)).fetchall()
        self.fill_table(self.transfers_table,[(when,source,target,money(cents),note)
                                              for when,source,target,cents,note in transfer_rows])
        self.transfers_empty_hint.setVisible(not bool(transfer_rows))
        card_rows=cards(self.db,pid)
        self._row_ids['card']=[c[0] for c in card_rows]
        self.fill_table(self.card_table,[(name,str(cut),str(due),money(lim),money(debt)) for _,name,cut,due,lim,debt in card_rows])
        limit_total=sum(c[4] for c in card_rows)
        debt_total=sum(c[5] for c in card_rows)
        self.card_total_label.setText(money(debt_total))
        self.card_limit_label.setText(money(limit_total))
        self.card_available_label.setText(money(max(0,limit_total-debt_total)))
        self.cards_empty_hint.setVisible(not bool(card_rows))
        self._selection_changed('card')
        self.fill_table(self.due_table,[(name,due,money(cents),cat,note) for name,due,cents,cat,note in upcoming(self.db,pid)])
        self.fill_table(self.dashboard_due,[(due,name,money(cents)) for name,due,cents,cat,note in upcoming(self.db,pid)[:7]])
        shared_rows=shared_history(self.db) if pid==2 else []
        self.fill_table(self.shared_table,[(tid,date_,acct,cat,money(cents),splits) for tid,date_,acct,cat,cents,splits in shared_rows])
        self.shared_empty_hint.setVisible(not bool(shared_rows))
        kmh_rows=overdraft(self.db,pid)
        self._row_ids['kmh']=[o[0] for o in kmh_rows]
        self.fill_table(self.kmh_table,[(name,money(limit),money(used),money(limit-used)) for oid,aid,name,limit,used in kmh_rows])
        self.kmh_limit_total.setText(money(sum(item[3] for item in kmh_rows)))
        self.kmh_used_total.setText(money(sum(item[4] for item in kmh_rows)))
        self.kmh_available_total.setText(money(sum(item[3]-item[4] for item in kmh_rows)))
        self.kmh_empty_hint.setVisible(not bool(kmh_rows))
        self._selection_changed('kmh')
        self.update_kmh_details()
        self.refresh_calendar()
        if hasattr(self,'rec_table'):
            recurring_items=upcoming_items(self.db,pid,months_ahead=6)
            self.fill_table(self.rec_table,[(i,n,'Fatura' if kind=='bill' else 'Abonelik',due,money(amt),cat,'Gecikmiş' if due<date.today().isoformat() else 'Bekliyor') for i,n,kind,due,amt,cat in recurring_items])
            self.rec_empty_hint.setVisible(not bool(recurring_items))
        document_rows=list_docs(self.db,pid)
        self.fill_table(self.doc_table,[(did,name,TYPES.get(typ,typ),status,when) for did,name,typ,status,when,_ in document_rows])
        self.doc_empty_hint.setVisible(not bool(document_rows))
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
            recurring_rows=[(name,'Fatura' if kind=='bill' else 'Abonelik',due,money(amt),
                             'Gecikmiş' if due<date.today().isoformat() else 'Bekliyor')
                            for _,name,kind,due,amt,_ in upcoming_items(self.db,self.pid(),months_ahead=3)]
            self.fill_table(self.calendar_recurring,recurring_rows)
            self.calendar_recurring_empty_hint.setVisible(not bool(recurring_rows))
        code=self.calendar_filter.currentData() or 'all'
        visible=filter_calendar(rows,code)
        today=date.today().isoformat()
        def status(due):
            return 'Gecikti' if due<today else ('Bugün' if due==today else 'Bekliyor')
        self.fill_table(self.calendar_table,[(iid,name,due,money(amount),status(due),note) for iid,name,due,amount,note in visible])
        self.calendar_empty_hint.setVisible(not bool(visible))

    def refresh_charts(self,pid):
        cat_rows=category_expenses(self.db,pid)
        def chart_slices(rows):
            rows=list(rows)
            if len(rows)>6:
                return rows[:5]+[('Diğer',sum(value for _,value in rows[5:]))]
            return rows
        self.category_chart.set_values(chart_slices([(str(k),v) for k,v in cat_rows]))
        self.trend_chart.set_values(monthly_trend(self.db,pid))
        accts=accounts_with_balances(self.db,pid)
        self.asset_chart.set_values(chart_slices(sorted([(name,balance) for _,name,kind,balance in accts if balance>0],key=lambda row:row[1],reverse=True)))

    def create_backup(self):
        from backup_manager import make_backup
        filename,_=QFileDialog.getSaveFileName(self,'Yedek oluştur',str(Path.home()/'Documents'/('ParaNoya-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip')),'Yedek (*.zip)')
        if not filename:return
        try:
            make_backup(DB_DIR,filename)
            QMessageBox.information(self,'Yedek hazır','Veritabanı ve ek belgeler doğrulandı.\n'+filename)
        except Exception as exc:QMessageBox.warning(self,'Yedek alınamadı',str(exc))

    def restore_from_backup(self):
        from backup_manager import verify_backup
        controller=getattr(self,'update_controller',None)
        if controller is not None and controller.is_busy:
            QMessageBox.information(self,'İşlem sürüyor','Güncelleme işlemi tamamlandıktan sonra yeniden deneyin.');return
        filename,_=QFileDialog.getOpenFileName(self,'Geri yüklenecek yedeği seç','','Yedek (*.zip)')
        if not filename:return
        try:verify_backup(filename)
        except Exception as exc:
            QMessageBox.warning(self,'Yedek geçersiz',str(exc));return
        if QMessageBox.question(self,'Yedekten geri yükle',
                'Diğer ParaNoya pencerelerini kapatın. Mevcut kayıtlar seçilen yedekle değiştirilecek.\n'
                'Mevcut veri klasörünün tamamı ayrı bir kurtarma kopyası olarak korunacak.\n'
                'Uygulama kapanıp yeniden açılacak. Devam edilsin mi?',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self._pending_restore=filename
        self.setEnabled(False)
        self.close()

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
            QLabel {{background:transparent;}}
            QFrame#cardMetric QLabel, QFrame#cardDetails QLabel, QGroupBox QLabel {{background:transparent;}}
            QWidget#sidebar {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #031d36,stop:0.6 #083452,stop:1 #065365);border:1px solid #275d79;border-radius:18px;color:white;}}
            QScrollArea#sidebarMenuScroll {{background:transparent;border:none;}}
            QWidget#sidebarMenuContent {{background:#092d49;}}
            QScrollArea#sidebarMenuScroll QScrollBar:vertical {{background:#092d49;width:7px;margin:0;}}
            QScrollArea#sidebarMenuScroll QScrollBar::handle:vertical {{background:#38718b;min-height:32px;border-radius:3px;}}
            QScrollArea#sidebarMenuScroll QScrollBar::add-line:vertical,QScrollArea#sidebarMenuScroll QScrollBar::sub-line:vertical {{height:0;}}
            QWidget#brandPanel {{background:#092d49;border:1px solid #174763;border-radius:12px;}}
            QWidget#brandPanel QLabel {{background:transparent;color:#ffffff;}}
            QWidget#brandPanel QLabel#mascotAvatar {{background:transparent;border:none;}}
            QWidget#sidebar QLabel {{color:#eefbff;background:transparent;}}
            QWidget#sidebar QPushButton {{color:#eefbff;background:#123e5c;border:1px solid #275773;}}
            QWidget#sidebar QPushButton:disabled {{color:#8daabd;background:#0b304d;border:1px solid #16415c;}}
            QWidget#sidebar QComboBox {{color:#eefbff;background:#123e5c;}}
            QFrame#cardMetric, QFrame#cardDetails {{background:{card};border:1px solid {border};border-radius:14px;}}
            QFrame#cardActionBar {{background:{card};border:1px solid {border};border-radius:12px;}}
            QFrame#cardActionBar QPushButton {{background:{'#183c57' if self.dark else '#eaf6ff'};border:1px solid {'#32627e' if self.dark else '#c6e4f7'};color:{ink};}}
            QFrame#cardActionBar QPushButton:hover {{background:#008d9a;color:white;}}
            QLabel#documentSafetyNote {{background:{'#183c50' if self.dark else '#e9f5fb'};color:{ink};border:1px solid {border};border-radius:9px;padding:11px 14px;font-size:12px;}}
            QLabel#sectionTitle {{font-size:21px;font-weight:800;color:{ink};}}
            QLabel#sectionSubtitle {{font-size:12px;color:{muted};}}
            QLabel#sectionSubheading {{font-size:15px;font-weight:800;color:{ink};padding-top:6px;}}
            QLineEdit#transactionSearch {{min-height:25px;padding:9px 14px;}}
            QPushButton#transactionClear {{min-height:25px;padding:9px 15px;}}

            QLabel#accountEmptyHint {{color:{muted};font-size:12px;padding:9px 12px;background:{card};border:1px dashed {border};border-radius:8px;}}
            QLabel#accountDetailBody {{color:{muted};font-size:12px;}}
            QPushButton#accountPrimaryAction {{background:#087f94;color:#ffffff;border:1px solid #0da1b5;font-weight:800;border-radius:10px;padding:10px 18px;}}
            QPushButton#accountPrimaryAction:hover {{background:#0b9db3;}}
            QLabel#metricCaption {{color:{muted};font-weight:700;font-size:11px;}}
            QLabel#metricNumber {{font-size:23px;font-weight:800;color:{ink};}}
            QLabel#cardDetailHeading {{font-size:16px;font-weight:800;color:{ink};}}
            QGroupBox {{background:{card};border:1px solid {border};border-radius:16px;margin-top:15px;padding:14px;font-weight:600;}}
            QGroupBox::title {{subcontrol-origin:margin;left:14px;padding:0 7px;}}
            QPushButton {{background:{surface};border:1px solid {border};padding:10px 14px;border-radius:9px;font-weight:600;}}
            QPushButton:hover {{background:#087f94;color:white;}}
            QPushButton:disabled {{color:#8298a9;}}
            QPushButton[nav='true'] {{text-align:left;padding:10px 14px;background:transparent;border:1px solid transparent;border-radius:9px;min-height:22px;color:#dceef7;font-weight:600;}}
            QPushButton[nav='true']:hover {{background:#164967;border-color:#28647e;}}
            QPushButton[nav='true'][active='true'] {{background:#087f98;border-color:#16a8bb;color:#ffffff;font-weight:800;}}
            QPushButton[nav='true'][active='true']:hover {{background:#0791aa;}}
            QPushButton[nav='true']:focus {{border-color:#6fe2e6;}}
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
            QLabel#dashboardSubtitle {{font-size:12px;color:{muted};}}
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
            QFrame#quickActions {{background:{card};border:1px solid {border};border-radius:14px;}}
            QLabel#quickActionsTitle {{color:{ink};font-size:13px;font-weight:700;}}
            QFrame#quickActions QPushButton {{background:{'#183c57' if self.dark else '#eaf6ff'};border:1px solid {'#32627e' if self.dark else '#c6e4f7'};color:{ink};}}
            QFrame#quickActions QPushButton:hover {{background:#008d9a;color:white;}}
            QScrollArea#dashboardScroll {{background:transparent;border:none;}}
            QScrollArea#dashboardScroll QScrollBar:vertical {{background:transparent;width:9px;margin:0;}}
            QScrollArea#dashboardScroll QScrollBar::handle:vertical {{background:{'#426580' if self.dark else '#b6cad7'};min-height:42px;border-radius:4px;}}
            QScrollArea#dashboardScroll QScrollBar::add-line:vertical,QScrollArea#dashboardScroll QScrollBar::sub-line:vertical {{height:0;}}
            QScrollArea#dashboardScroll QScrollBar::add-page:vertical,QScrollArea#dashboardScroll QScrollBar::sub-page:vertical {{background:transparent;}}
            QLabel#dashboardFoot {{color:{muted};font-size:12px;}}
            QProgressBar {{border:0;border-radius:6px;background:{border};height:8px;}}
            QProgressBar::chunk {{background:#18c6b5;border-radius:6px;}}
        """)
        self.style().unpolish(self);self.style().polish(self)
        self.stack.widget(0).verticalScrollBar().setStyleSheet(
            'QScrollBar:vertical {background:'+('#102f47' if self.dark else '#e6f1f7')+';width:8px;margin:0;border:0;}'
            'QScrollBar::handle:vertical {background:'+('#46718c' if self.dark else '#a0bacb')+';min-height:44px;border-radius:4px;}'
            'QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;border:0;}'
            'QScrollBar::up-arrow:vertical,QScrollBar::down-arrow:vertical {width:0;height:0;}'
            'QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:transparent;}')
        for chart in (self.category_chart, self.trend_chart, self.asset_chart):
            chart.setProperty('darkTheme', self.dark)
            chart.update()
        self._mark_active_nav()

    def _mark_active_nav(self):
        selected=self.stack.currentIndex()
        for page_index,button in self.nav_map.items():
            active=page_index==selected
            if button.property('active') != active:
                button.setProperty('active',active)
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()

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
    from PySide6.QtCore import QLockFile
    app = QApplication(sys.argv)
    # The lock lives outside the directory which recovery may rename.
    DB_DIR.parent.mkdir(parents=True,exist_ok=True)
    application_lock=QLockFile(str(DB_DIR.parent/(DB_DIR.name+'.paranoya.lock')))
    application_lock.setStaleLockTime(0)
    if not application_lock.tryLock(0):
        QMessageBox.information(None,'ParaNoya zaten açık','Bu veri klasörü başka bir ParaNoya penceresinde açık. Önce o pencereyi kapatın.')
        return
    from backup_manager import recover_interrupted_restore
    try:recover_interrupted_restore(DB_DIR)
    except Exception as exc:
        QMessageBox.critical(None,'Veri kurtarma gerekli',str(exc))
        return
    # Capture a consistent snapshot BEFORE changing the schema.
    DB_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        with closing(sqlite3.connect(DB_PATH)) as source:
            old_version = source.execute('PRAGMA user_version').fetchone()[0]
            if old_version < 8:
                backup_name='ailefinans.before_v08_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db'
                with closing(sqlite3.connect(DB_DIR / backup_name)) as target:
                    source.backup(target)
    try:
        migrate()
    except Exception as exc:
        print('Veritabanı açılamadı / güncellenemedi:', exc, file=sys.stderr)
        raise
    with closing(open_db()) as db:
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
    result=app.exec()
    pending=getattr(window,'_pending_restore',None)
    if pending:
        from backup_manager import restore_backup
        try:
            recovery=restore_backup(pending,DB_DIR,confirmed=True)
            QMessageBox.information(None,'Geri yükleme tamamlandı','Önceki kayıtlarınızın kurtarma klasörü:\n'+str(recovery))
        except Exception as exc:
            QMessageBox.warning(None,'Geri yükleme tamamlanamadı',str(exc))
        application_lock.unlock()
        import subprocess
        command=[sys.executable]
        if not getattr(sys,'frozen',False):command.append(str(Path(__file__).resolve()))
        subprocess.Popen(command,shell=False,close_fds=True)
    application_lock.unlock()
    sys.exit(result)


if __name__ == '__main__':
    if '--smoke-test' in sys.argv:
        from packaging_smoke import run
        run()
    else:
        main()
