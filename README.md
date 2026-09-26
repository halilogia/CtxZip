# CtxZip

**AI kodlama oturumlarını proje bazında arşivle, kademeli özetle ve yeni sohbete bağlam taşı.**

CtxZip, Claude Code ve Codex yerel oturumlarını, Antigravity'nin erişilebilen Markdown artefaktlarını toplar. Ham kayıtları saklar, okunabilir dökümler, **Bölüm** ve **Cilt** özetleri üretir. Yeni görev için token bütçeli `BAGLAM.md` hazırlar. Python 3.10+ standart kütüphanesi yeterlidir.

CLI `ctxzip.py` içindedir; kaynak ayrıştırıcıları, Bölüm/Cilt özetleme akışı ve durum dosyaları ile gizlilik, LLM ve Git sınırları `ctxzip_core/` modüllerindedir. Komutlar ve arşiv biçimi değişmedi.

Yeni Python kaynak dosyaları, semboller, parametreler, yorumlar ve docstring'ler İngilizce adlandırılır. Eski Python kullanıcıları için Türkçe isimler uyumluluk takma adları olarak korunur; mevcut arşiv klasörleri ve durum JSON anahtarları taşınmaz. Örnek ayar dosyası `ctxzip.settings.example.json`, özel ayar dosyası `ctxzip.settings.json` adını kullanır. Eski `ctxzip_ayar.json` dosyası İngilizce dosya yoksa otomatik yüklenir; ikisi de varsa İngilizce dosya seçilir.

CLI Türkçe ve İngilizce sunar. Ayar dosyasındaki `"language": "tr"` varsayılandır; `"en"` İngilizce arayüz ve yeni özet istemleri üretir. Öncelik sırası `--language`, `CTXZIP_LANG`, ayar dosyasıdır. İngilizce komut takma adları (`collect`, `transcript`, `summarize`, `context`, `all`, `status`) Türkçe komutlarla beraber kullanılabilir. Var olan özetler seçilen dilde yeniden yazılmaz.

Çeviriler `locales/<language>/<namespace>.json` altında namespace'lere ayrılır (ör. `locales/en/cli.json` ve `locales/tr/cli.json`). Yeni arayüz metni eklerken aynı anahtarı iki dilin uygun namespace dosyasına ekleyin; parametreleri `{{project}}` biçimindeki isimli yer tutucularla yazın. Başlangıçta `validate_catalogs()` anahtar, yer tutucu ve çoğul biçim uyumunu denetler. Locale `en-US` gibi bölgesel bir değerle verilirse temel dile (`en`) normalize edilir; desteklenmeyen dil reddedilir. `i18n.translate(language, "namespace:key", ...)` yeni kod için önerilen API'dir. Bu, Python standart kütüphanesiyle çalışan namespace tabanlı bir kataloğudur; JavaScript i18next paketine çalışma zamanı bağımlılığı yoktur.

```powershell
python ctxzip.py --language en --help
python ctxzip.py --language en all --manual
python ctxzip.py --language tr durum
```

> **Durum:** Erken sürüm (`0.1.0`). Claude Code ve Codex yerel kayıtlarıyla içe aktarma denendi. Antigravity desteği tam sohbet geçmişini kapsamaz. Gerçek LLM ile özet kalitesi henüz doğrulanmadı.

## Hızlı başlangıç

```powershell
git clone https://github.com/halilogia/CtxZip.git
cd CtxZip
Copy-Item ctxzip.settings.example.json ctxzip.settings.json
# Set llm.model in ctxzip.settings.json to a model available from your provider.
python ctxzip.py hepsi
python ctxzip.py durum
python ctxzip.py baglam Proje-Adi --token 12000
```

LLM bağlantısı kurmadan ilerlemek için `python ctxzip.py hepsi --elle` çalıştırın. Oluşan `*.istem.md` dosyalarının yanıtlarını ilgili Bölüm dosyalarındaki `<!-- BURAYA-YAPISTIR -->` yerine koyun. Model adı boş veya örnek değerken otomatik özetleme çalıştırmayın.

Otomatik özetlemede her LLM isteğinin **tam sistem ve kullanıcı metni** ile hedef adresi terminalde gösterilir. Varsayılan olarak her istek için `e` yanıtıyla onay gerekir; etkileşimsiz çalışmada gönderim durdurulur. Metni önceden denetlediğiniz otomasyonlarda `ozetle --onayli-gonder` veya `hepsi --onayli-gonder` kullanılabilir. Bu seçenek etkileşimli onayı atlar; önizleme yine gösterilir. Terminal çıktısını da hassas veri kabul edin.

| Komut | İşlev |
| --- | --- |
| `topla` | Kaynak oturumları kişisel arşive kopyalar; büyüyen dosyaları günceller. |
| `dokum [--proje AD]` | Ham kayıttan okunabilir döküm oluşturur. |
| `ozetle [--proje AD] [--elle]` | Bölüm ve yeterli Bölümden Cilt oluşturur. |
| `hepsi [--elle]` | Toplama, döküm ve özetlemeyi sırayla yapar. |
| `baglam AD [--token 12000] [--kopyala YOL]` | `BAGLAM.md` üretir. |
| `durum` | Proje ve bekleyen özet sayılarını gösterir. |

## Veri akışı

```text
Claude Code / Codex / Antigravity artefaktları / elle eklenen metin
      → raw/ → dokum/ → bolumler/ → ciltler/ → BAGLAM.md
```

Varsayılan arşiv `~/CtxZip-Arsiv` içindedir. `bolum_token` yaklaşık Bölüm bütçesini, `cilt_bolum_sayisi` bir Cilt için Bölüm sayısını, `aktif_oturum_dk` aktif oturumun son parçasını bekletme süresini ayarlar. `llm.base_url` OpenAI uyumlu uç noktadır; örnekte yerel 9Router adresi bulunur. Anahtar gerekiyorsa `CTXZIP_API_KEY` ortam değişkenini kullanın.

`BAGLAM.md` eski oturumların özetidir. Güncel kod, Git durumu ve test sonuçlarıyla çelişirse onlar geçerlidir. `--kopyala` bir Git deposuna yazacaksa hedef dosyanın izlenmemesi ve hedef deponun `.gitignore` kurallarıyla dışlanması gerekir; aksi hâlde kopya durdurulur.

## Güvenlik ve sınırlar

- Bu klonda commit öncesi korumayı kurmak için `python scripts/install_hook.py` çalıştırın. Kurulum var olan `pre-commit` hook'unu yedekleyip korur. Koruma Git index'ine seçilmiş dosyaları tarar; kişisel arşiv/ayar yollarını, yaygın sır kalıplarını ve tam kullanıcı ev yollarını engeller. Bu, bilinmeyen sırları yakalama garantisi değildir ve `git commit --no-verify` ile atlanabilir.
- `raw/` sohbet metni ve olası sırlar içerir. Arşivi, `ctxzip.settings.json` ayar dosyasını ve `BAGLAM.md` çıktısını açık depoya koymayın. Eski `ctxzip_ayar.json` dosyaları da otomatik yüklenir.
- Döküm ve model isteminde bilinen anahtar kalıpları maskelenir; bu eksiksiz bir sır taraması değildir. Otomatik özetlemede metin seçilen sağlayıcıya gönderilir; `--elle` otomatik ağ çağrısı yapmaz.
- Token hesabı yaklaşık `karakter/3.5` değeridir. Bağlam seçimi şu an görev ilgisinden çok yeniliğe dayanır.
- Antigravity için yalnızca bulunan `brain/<id>/*.md` dosyaları alınır. Bulut oturumları kendiliğinden yerel arşive gelmez; dışa aktarılan kayıtlar ilgili projenin `gelen/` klasörüne konabilir.

## Geliştirme doğrulaması

`python -m unittest discover -s tests -v` ve `python ctxzip.py --help` çalıştırın. Testler geçici dizinlerde sentetik kayıtlarla tekrar çalıştırma, kaynak büyümesi/kısalması, elle düzenleme, hata sonrası devam ve gizlilik sınırlarını denetler. Gerçek sağlayıcı bağlantısını veya tüm kaynak sürümlerini doğrulamaz.

## Belgeler

[Ajan kılavuzu](AGENTS.md) · [Mimari](ARCHITECTURE.md) · [Yol haritası](ROADMAP.md) · [Plan](docs/PLAN.md) · [Görevler](docs/TASKS.md) · [Teknik bilgi](docs/KNOWLEDGE.md) · [Değişiklikler](CHANGELOG.md)

## Lisans

[GPL-3.0](LICENSE) © Halil Emre
