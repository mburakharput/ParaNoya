import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize
from bank_logo_renderer import bank_icon, menu_icon
from ailefinans import App

class BankVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_symbol_logo_is_fully_visible(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'symbol.svg'
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 20"><symbol id="logo" viewBox="-50 -10 100 20"><rect x="-50" y="-10" width="40" height="20" fill="red"/><rect x="10" y="-10" width="40" height="20" fill="blue"/></symbol><use href="#logo" x="-50" y="-10" width="100" height="20" transform="translate(50 10)"/></svg>')
            image = bank_icon(path).pixmap(QSize(96,24),1).toImage()
            self.assertGreater(image.pixelColor(10,12).red(), 200)
            self.assertGreater(image.pixelColor(85,12).blue(), 200)

    def test_bundled_ziraat_dinamik_has_logo_and_transparent_text_gutter(self):
        from bank_logo_manager import logo_path
        path=logo_path('Ziraat Dinamik')
        self.assertIsNotNone(path)
        icon=menu_icon(path)
        self.assertFalse(icon.isNull(),'Bundled original logo must decode successfully')
        image=icon.pixmap(QSize(110,24),3).toImage()
        self.assertEqual(image.width(),330)
        self.assertGreater(sum(image.pixelColor(x,y).alpha()>0 for x in range(288) for y in range(72)),500)
        self.assertTrue(all(image.pixelColor(x,y).alpha()==0 for x in range(288,330) for y in range(72)))

    def test_turkish_bank_is_not_offered(self):
        from ailefinans import list_bank_names
        from bank_logo_manager import LOGO_IDS
        self.assertNotIn('Turkish Bank',list_bank_names())
        self.assertNotIn('Turkish Bank',LOGO_IDS)

    def test_raster_logo_cannot_paint_over_menu_text_at_different_dpr(self):
        from PySide6.QtGui import QPixmap,QIcon,QColor
        from unittest.mock import patch
        large=QPixmap(288,72);large.fill(QColor('red'));large.setDevicePixelRatio(1)
        with patch('bank_logo_renderer.bank_icon',return_value=QIcon(large)):
            image=menu_icon(None).pixmap(QSize(110,24),3).toImage()
        self.assertTrue(all(image.pixelColor(x,y).alpha()==0 for x in range(288,330) for y in range(72)))

    def test_clipped_wordmark_does_not_become_solid_rectangle(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sekerbank.svg'
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 20"><defs><clipPath id="clip"><path d="M0 0 L100 20 L0 20 Z"/></clipPath></defs><g clip-path="url(#clip)"><rect width="100" height="20" fill="green"/></g></svg>')
            image = bank_icon(path).pixmap(QSize(96,24),1).toImage()
            self.assertEqual(image.pixelColor(85,5).alpha(), 0)
            self.assertGreater(image.pixelColor(10,18).alpha(), 200)

    def test_menu_gutter_is_transparent_at_high_dpi(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'logo.svg'
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 20"><rect width="100" height="20" fill="red"/></svg>')
            image = menu_icon(path).pixmap(QSize(110,24),3).toImage()
            self.assertEqual(image.width(),330)
            self.assertTrue(all(image.pixelColor(x,y).alpha()==0
                                for x in range(288,330) for y in range(72)))

    def test_logo_bounds_are_stable_across_display_scaling(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'wide.svg'
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 30"><rect width="1000" height="30" fill="red"/></svg>')
            for density in (1,1.5,2,3):
                pix=menu_icon(path).pixmap(QSize(110,24),density)
                self.assertLessEqual(pix.width()/pix.devicePixelRatio(),110)
                self.assertLessEqual(pix.height()/pix.devicePixelRatio(),24)
                self.assertFalse(pix.isNull())

    def test_mascot_image_keeps_transparency_without_white_rim(self):
        from PySide6.QtGui import QColor, QImage, QPainter
        from PySide6.QtCore import Qt
        from ailefinans import circular_mascot
        # A generated transparent circular asset must not gain a white backdrop.
        with tempfile.TemporaryDirectory() as folder:
            icon_path=Path(folder)/'transparent-owl-sample.png'
            source=QImage(60,60,QImage.Format.Format_ARGB32)
            source.fill(Qt.GlobalColor.transparent)
            painter=QPainter(source)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#008e9f'))
            painter.drawEllipse(3,3,54,54)
            painter.end()
            self.assertTrue(source.save(str(icon_path)))
            image=circular_mascot(icon_path).toImage()
            self.assertFalse(image.isNull())
            self.assertEqual(image.pixelColor(0,0).alpha(),0)
            self.assertEqual(image.pixelColor(image.width()-1,0).alpha(),0)
            self.assertEqual(image.pixelColor(image.width()//2,4).name(),'#008e9f')
            self.assertGreater(image.pixelColor(image.width()//2,image.height()//2).alpha(),200)
        # The bundled real owl must also load successfully.
        owl=circular_mascot(Path(__file__).parent/'assets'/'paranoya_mascot.png').toImage()
        self.assertFalse(owl.isNull())
        self.assertEqual(owl.pixelColor(0,0).alpha(),0)
        self.assertGreater(owl.pixelColor(owl.width()//2,owl.height()//2).alpha(),200)

    def test_recurring_form_keeps_scrollable_minimum_height(self):
        """At minimum window size the form must scroll, never compress input controls."""
        import inspect
        source=inspect.getsource(App.__init__)
        self.assertIn('recurring_page.setMinimumHeight(930)',source)
        self.assertIn('entry.setMinimumHeight(425)',source)
        self.assertIn('widget.setMinimumHeight(42)',source)
        self.assertIn('QSizePolicy.Policy.Fixed',source)
        self.assertIn('recurring_scroll.setWidget(recurring_page)',source)
        self.assertIn('self.stack.addWidget(recurring_scroll)',source)

    def test_content_page_scrolls_without_compressing_form_at_920x600(self):
        """Compact Windows windows should scroll instead of squeezing page contents."""
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QScrollArea
        page=QWidget()
        layout=QVBoxLayout(page)
        fields=[]
        for _ in range(8):
            field=QLineEdit()
            field.setMinimumHeight(42)
            layout.addWidget(field)
            fields.append(field)
        scroll=App._scroll_content_page(page,'compactPageScroll',900)
        try:
            self.assertIsInstance(scroll,QScrollArea)
            self.assertIs(scroll.widget(),page)
            self.assertEqual(page.minimumHeight(),900)
            scroll.resize(640,440)
            scroll.show()
            self.app.processEvents()
            self.assertGreater(scroll.verticalScrollBar().maximum(),0)
            self.assertTrue(all(field.height()>=42 for field in fields))
        finally:
            scroll.close()

    def test_all_content_pages_use_scrollable_viewport(self):
        """Page order must stay intact while long panels gain a scroll container."""
        import inspect
        source=inspect.getsource(App.__init__)
        names=['accounts_page','transactions_page','family_page','transfer_page',
               'cardpage','historypage','kmhpage','calpage','documents_page',
               'products_page']
        for page in names:
            self.assertIn('self.stack.addWidget(self._scroll_content_page('+page+',',source)

    def test_missing_logo_detail_uses_fixed_size_fallback(self):
        from PySide6.QtWidgets import QLabel
        host=SimpleNamespace(_bank_icon=lambda name: App._bank_icon(None,name),devicePixelRatioF=lambda:2)
        label=QLabel()
        App._set_detail_logo(host,label,'Bilinmeyen Banka')
        self.assertEqual(label.size(),QSize(110,34))
        self.assertFalse(label.hasScaledContents())
        self.assertFalse(label.isHidden())

    def test_bank_metadata_resolves_custom_nicknames_without_guessing(self):
        db=sqlite3.connect(':memory:')
        try:
            db.executescript("""
                CREATE TABLE accounts(id INTEGER, name TEXT, profile_id INTEGER);
                CREATE TABLE account_bank_details(account_id INTEGER,bank_name TEXT);
                CREATE TABLE credit_cards(id INTEGER,name TEXT,profile_id INTEGER);
                CREATE TABLE card_catalog_links(card_id INTEGER,bank TEXT);
                INSERT INTO accounts VALUES(1,'Maaşım',1),(2,'Ortak',1),(3,'Ortak',1);
                INSERT INTO account_bank_details VALUES(1,'Enpara Bank'),(2,'Akbank'),(3,'Şekerbank');
                INSERT INTO credit_cards VALUES(9,'Market kartım',1);
                INSERT INTO card_catalog_links VALUES(9,'Şekerbank');
            """)
            host=SimpleNamespace(db=db,pid=lambda:1)
            host._bank_aliases=App._build_bank_aliases(host)
            self.assertEqual(App._bank_for_text(host,'Maaşım (1.000 TL)'),'Enpara Bank')
            self.assertEqual(App._bank_for_text(host,'Market kartım'),'Şekerbank')
            self.assertEqual(App._bank_for_text(host,'Ortak'),'')
            self.assertEqual(App._bank_for_text(host,'Bilinmiyor'),'')
        finally:
            db.close()

    def test_bank_menus_keep_item_data_and_consistent_logo_spacing(self):
        from PySide6.QtWidgets import QWidget, QComboBox, QTableWidget
        from PySide6.QtGui import QIcon
        host=SimpleNamespace(_bank_aliases={'Maaşım': {'Enpara Bank'},'Şekerbank': {'Şekerbank'}})
        host._bank_for_text=lambda text: App._bank_for_text(host,text)
        host._bank_icon=lambda name: QIcon()
        root=QWidget()
        account=QComboBox(root)
        account.addItem('Maaşım (1.000 TL)',17)
        card=QComboBox(root)
        card.addItem('Şekerbank — Kart',('Şekerbank','Kart'))
        App._decorate_bank_widgets(host,root)
        self.assertEqual(account.itemData(0),17)
        self.assertEqual(card.itemData(0),('Şekerbank','Kart'))
        for combo in (account,card):
            self.assertEqual(combo.iconSize(),QSize(110,24))
            self.assertEqual(combo.maximumWidth(),420)
            self.assertEqual(combo.maxVisibleItems(),5)
        table=QTableWidget(0,1)
        table.setHorizontalHeaderLabels(['Hesap'])
        App.fill_table(host,table,[('Maaşım',)])
        self.assertEqual(table.item(0,0).text(),'Maaşım')
        self.assertEqual(table.iconSize(),QSize(110,24))
