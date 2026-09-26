# CtxZip

**AI kodlama oturumlarını proje bazında arşivle, kademeli özetle ve yeni sohbete bağlam taşı.**

CtxZip, Claude Code ve Codex yerel oturumlarını, Antigravity'nin erişilebilen Markdown artefaktlarını ve sınırlı ChatGPT JSON dışa aktarımlarını toplar. Ham kayıtları saklar, okunabilir dökümler, **Bölüm** ve **Cilt** özetleri üretir. Yeni görev için token bütçeli `BAGLAM.md` hazırlar. Python 3.10+ standart kütüphanesi yeterlidir.

CLI `ctxzip.py` içindedir; kaynak keşfi/kopyalama, transcript üretimi, bağlam paketi oluşturma, kaynak ayrıştırıcıları, Bölüm/Cilt özetleme akışı ve durum dosyaları ile gizlilik, LLM ve Git sınırları `ctxzip_core/` modüllerindedir. Komutlar ve arşiv biçimi değişmedi.

Yeni Python kaynak dosyaları, semboller, parametreler, yorumlar ve docstring'ler İngilizce adlandırılır. Eski Python kullanıcıları için Türkçe isimler uyumluluk takma adları olarak korunur; mevcut arşiv klasörleri ve durum JSON anahtarları taşınmaz. Örnek ayar dosyası `ctxzip.settings.example.json`, özel ayar dosyası `ctxzip.settings.json` adını kullanır. Eski `ctxzip_ayar.json` dosyası İngilizce dosya yoksa otomatik yüklenir; ikisi de varsa İngilizce dosya seçilir.

CLI Türkçe ve İngilizce sunar. Ayar dosyasındaki `"language": "tr"` varsayılandır; `"en"` İngilizce arayüz ve yeni özet istemleri üretir. Öncelik sırası `--language`, `CTXZIP_LANG`, ayar dosyasıdır. İngilizce komut takma adları (`collect`, `transcript`, `summarize`, `context`, `all`, `status`) Türkçe komutlarla beraber kullanılabilir. Var olan özetler seçilen dilde yeniden yazılmaz.

Çeviriler `locales/<language>/<namespace>.json` altında namespace'lere ayrılır (ör. `locales/en/cli.json` ve `locales/tr/cli.json`). Yeni arayüz metni eklerken aynı anahtarı iki dilin uygun namespace dosyasına ekleyin; parametreleri `{{project}}` biçimindeki isimli yer tutucularla yazın. Başlangıçta `validate_catalogs()` anahtar, yer tutucu ve çoğul biçim uyumunu denetler. Locale `en-US` gibi bölgesel bir değerle verilirse temel dile (`en`) normalize edilir; desteklenmeyen dil reddedilir. `i18n.translate(language, "namespace:key", ...)` yeni kod için önerilen API'dir. Bu, Python standart kütüphanesiyle çalışan namespace tabanlı bir kataloğudur; JavaScript i18next paketine çalışma zamanı bağımlılığı yoktur.

```powershell
python ctxzip.py --language en --help
python ctxzip.py --language en all --manual
python ctxzip.py --language tr durum
```

> **Durum:** Erken sürüm (`0.1.0`). Claude Code ve Codex yerel kayıtlarıyla içe aktarma denendi. ChatGPT dışa aktarımı yalnızca sentetik örnekle sınandı; gerçek dışa aktarımla henüz doğrulanmadı. Antigravity desteği tam sohbet geçmişini kapsamaz. Gerçek LLM ile özet kalitesi henüz doğrulanmadı.

## Hızlı başlangıç

Windows, macOS ve Linux için kurulum ve zamanlanmış `--manual` toplama adımları [Kurulum ve zamanlama kılavuzunda](docs/INSTALLATION.md) bulunur.

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
| `topla` | Kaynak oturumları kişisel arşive kopyalar; değişen JSONL oturumlarının önceki sürümlerini içerik hash'iyle saklayıp etkin kopyayı günceller. |
| `dokum [--proje AD]` | Ham kayıttan okunabilir döküm oluşturur. |
| `ozetle [--proje AD] [--elle]` | Bölüm ve yeterli Bölümden Cilt oluşturur. |
| `hepsi [--elle]` | Toplama, döküm ve özetlemeyi sırayla yapar. |
| `baglam AD [--token 12000] [--task GÖREV] [--file YOL] [--symbol SEMBOL] [--commit SHA] [--from-git-diff] [--budget-profile priority|balanced] [--explain] [--kopyala YOL]` | `BAGLAM.md` üretir; görev, dosya, sembol, commit ve geçerli Git farkı sinyalleriyle tamamlanmış özetleri sıralayabilir. |
| `durum` | Proje ve bekleyen özet sayılarını gösterir. |
| `doctor` | Ayarları, Python/parser kayıtlarını, kaynak yollarını, yerel Git korumasını ve bağlantı yapılandırmasını salt okunur denetler. Ağ/LLM çağrısı yapmaz; sır değerlerini veya yapılandırılmış yolları yazdırmaz. |
| `test-run --project AD [--scope YOL]... -- KOMUT [ARGÜMAN...]` | Verilen yerel testi kabuksuz çalıştırır ve Git çalışma ağacı kimliğiyle sonucunu özel bilgi koleksiyonuna kaydeder. |

## Veri akışı

```text
Claude Code / Codex / Antigravity artefaktları / elle eklenen metin
      → raw/ → dokum/ → bolumler/ → ciltler/ → BAGLAM.md
```

Kaynak kapsamı: Claude Code ve Codex'in yerel JSONL kayıtları ham hâliyle saklanır; dökümler mesajları ve araç çağrılarını normalleştirir. Çekirdekte granular olay API'si bu iki JSONL kaynağını kapsar; ChatGPT ise her tur için tek transcript olayı üretir; event provenance etkin mapping düğümlerinin kimliklerini taşır, ancak gerçek dışa aktarma şemasıyla doğrulama henüz yapılmadı. Antigravity için bulunan her `brain/<id>/*.md` artefaktı, elle eklenen her metin dosyası gibi rol/araç yapısı çıkarılmadan kaynak atıflı genel bir transcript olayı üretir; Antigravity tam sohbet geçmişi değildir. İsteğe bağlı ChatGPT dışa aktarımı için ZIP'i kendiniz açıp ilgili projenin `gelen/` klasörüne `conversations.json`, `conversations-1.json` veya `conversations_1.json` biçimindeki JSON dosyasını koyun; `collect` her konuşmayı ayrı `raw/chatgpt/` oturumu olarak hazırlar ve kaynak dosyayı değiştirmez. Mevcut adaptör yalnızca `mapping` ve `current_node` içeren konuşma yapısının etkin ebeveyn zincirindeki metin parçalarını okur; araç çağrıları, ekler ve alternatif dallar döküme eklenmez. Bu şema kişisel verisi temizlenmiş sentetik örnekle sınanmıştır, gerçek dışa aktarımla henüz doğrulanmamıştır. ZIP doğrudan işlenmez ve her JSON dosyası otomatik içe aktarılmaz.

`collect` çalışırken değişen JSONL oturumunun önceki baytları, etkin ham kopya değiştirilmeden önce `*.onceki.jsonl` biçiminde içerik hash'li bir adla arşivlenir; tekrar toplama aynı sürüm için yeni kopya üretmez. Normal oturum listesi geçmiş sürüm dosyalarını etkin oturum saymaz. `dokum` çalışırken olaylar proje arşivindeki gizli `.ctxzip-events/` altında sürümlü, atomik JSON anlık görüntülerine yazılır. Kaynak içeriği veya parser sürümü değişince önce doğrulanmış eski olay anlık görüntüsü içerik adresli `.ctxzip-events/versions/` altına atomik yazılır, ardından güncel görünüm değiştirilir. Kaynak silinince de güncel görünüm kaldırılmadan önce geçmiş sürüm korunur. Bu olay geçmişi metin içerebilir ve özel arşiv verisidir; depoya eklemeyin. Değişen veya kaldırılan Antigravity artefaktları, etkin kopya güncellenmeden önce `raw/antigravity-history/` altında korunur; kaynak klasör silinmiş veya okunamıyorsa arşiv kopyası korunur. Bu özel olay dosyalarını Git'e eklemeyin.

Varsayılan arşiv `~/CtxZip-Arsiv` içindedir. `bolum_token` yaklaşık Bölüm bütçesini, `cilt_bolum_sayisi` bir Cilt için Bölüm sayısını, `aktif_oturum_dk` aktif oturumun son parçasını bekletme süresini ayarlar. `llm.base_url` OpenAI uyumlu uç noktadır; örnekte yerel 9Router adresi bulunur. Anahtar gerekiyorsa `CTXZIP_API_KEY` ortam değişkenini kullanın.

Çekirdekteki `KnowledgeStore` API'si görev, karar, kısıt, test kanıtı, açık soru ve dosya atıflarını özetlerden ayrı, kaynak bağlantılı koleksiyonlarda saklayabilir. `knowledge add` (Türkçe takma adı `hafiza add`) kullanıcı tarafından karar, kısıt, görev, açık soru veya dosya atfı eklenmesini sağlar. Önce `transcript` komutuyla kaynak olay anlık görüntüsünü oluşturun:

```powershell
python ctxzip.py knowledge add --project MyProject --kind decision `
  --source codex --session SESSION_ID --turn 12 `
  --text "Keep parser adapters independent from the CLI."
```

İlk CLI sürümü ayrıntılı olay sağlayan Claude Code, Codex ve ChatGPT kaynaklarını kabul eder. Metin CLI çıktısına yazılmaz ve LLM'e otomatik gönderilmez. `--supersedes` açık kullanıcı kararı gerektirir; kısıt değişimi aynı kapsamda olmalıdır. `test-run` yalnızca kendi çalıştırdığı komutun sonucunu ekler. Bu komut argümanları ve test çıktısını saklamaz; yalnızca çalıştırılabilir dosyanın adını, sonucu ve komut öncesi Git çalışma ağacı kimliğini kaydeder. Wrapper dışından çalıştırılan testler otomatik yakalanmaz. Var olan `knowledge/` koleksiyonları öncelik sıralı `BAGLAM.md` paketine eklenir. Test kanıtı, Git çalışma ağacıyla tam eşleşmediğinde güncel başarı olarak sunulmaz. Karar ve kısıt kayıtları isteğe bağlı geçerlilik yolları ve Git HEAD kaydı taşıyabilir; eski veya kapsamı eksik kayıtlar bağlamda bilinmiyor ya da muhtemelen eski olarak işaretlenir. Bir kısıt yalnızca aynı kapsamdaki kullanıcı onaylı yeni kısıt açıkça eskisini değiştiriyorsa geçersizleşir; çıkarım ajanları bunu yapamaz. Bilgi koleksiyonlarının v1/v2 biçimleri okunur ve sonraki yazımda v3 biçimine taşınır. `knowledge/` hem `.gitignore` hem de staged dosya korumasına dahildir.

Kaynak hash'i ve üretim dili bulunan, sonradan elle değiştirilmemiş Bölümler, bağlam hazırlanırken kayıtlı tur aralığının mevcut ham oturumla eşleşip eşleşmediği bakımından salt okunur denetlenir; hash karşılaştırması CLI'ın o anki dilinden etkilenmez. Hash'i değişen veya mevcut, okunabilir kaynağında artık tam tur aralığı bulunmayan Bölüm bağlama eklenmez; onu içeren Cilt de atlanır ve Cilt'teki güncel Bölümler ayrı aday olarak değerlendirilir. Parser sürümü değiştiyse de özet elenir. Balanced profilinde bu eski aralıklar ham tur tekrarını engellemez. Elle düzenlendiği hash metadata'sıyla doğrulanan özetler kullanıcı düzeltmesi kabul edilir; freshness denetimi onları elemez veya değiştirmez. Özet dosyası yazıldıktan sonra `durum.json` güncellenememişse, sonraki özetleme çalışması numarası ve kaynak aralığı tutarlı metadata taşıyan yetim Bölüm/Cilt dosyalarını, numarada boşluk olsa da duruma bağlar ve içeriğini değiştirmez. Elle modda işlem istem yazımından sonra kesilirse, yeniden deneme mevcut `*.istem.md` dosyasını ezmez; kullanıcı bu arada yaptığı düzenlemeyi korur. Yeni numaralar mevcut en büyük numaranın ardından verilir; Ciltler yalnızca ardışık numaralı Bölümleri kapsar. Metadata'sı eksik, tutarsız veya mevcut kaynak aralıklarıyla çakışan tanınmış dosya değiştirilmeden bırakılır ve özetleme durur. Eski arşivlerde kaynak hash'i/üretim dili yoksa, kaynak okunamıyorsa veya parser sürüm değişikliği karşılaştırmayı belirsiz kılıyorsa freshness doğrulanamaz; bu durumlar otomatik olarak güncel sayılmaz. Parser sürümü metadata'sı olmayan eski bir özette hash ve üretim dili mevcutsa kaynak hash'i yine karşılaştırılır; parser sürüm güncelliği bilinmiyor kalır.

`BAGLAM.md` sürümlü bir JSON metadata yorum bloğu ve okunabilir Markdown gövdesinden oluşur. Metadata; proje etiketi, üretim zamanı, dil, yaklaşık bütçe, seçili kaynak atıfları ve varsa Git snapshot kimliklerini taşır; mutlak depo yolu içermez. Format şeması `ctxzip-context-pack` kimliğiyle sürümlenir. `CONTEXT.md` adı gelecekteki geçiş için ayrılmıştır, mevcut çıktı ve kopyalama adı `BAGLAM.md` olarak kalır.

`BAGLAM.md` eski oturumların özetidir. Güncel kod, Git durumu ve test sonuçlarıyla çelişirse onlar geçerlidir. Örnek: `python ctxzip.py baglam Proje-Adi --task "parser timeout" --file src/parser.py --symbol parse_codex_session --commit abc123 --from-git-diff --explain`. Seçici sözcük örtüşmesi, tam dosya yolu, kod sembolü, commit, geçerli çalışma ağacındaki değişen yollar ve mevcutsa özet metadata'sındaki güncellik işaretini kullanır. Güncel Git farkındaki bir yol özetin metninde veya dosya metadata'sında tam olarak geçiyorsa bu bağlam üretiminde özet `possibly stale` olarak etiketlenir; kaynak özet dosyası değiştirilmez. İncelenmiş bir özete temiz Git deposunda `python ctxzip.py summary-validity --project Proje-Adi B0001.md --validity-path src/parser.py` komutuyla validity_paths ve validity_head_sha yazılır. Yalnızca verdiğiniz izlenen dosyalar kapsama girer; belirtilmeyen iddiaların güncelliği çıkarılmaz. BAGLAM.md üretirken `--from-git-diff` verilmişse bildirilen bir yol değiştiğinde veya HEAD farklı olduğunda özet olası eski işaretlenir. `--from-git-diff` komutu hedef projenin Git çalışma ağacından çağrılmalıdır; dosya/commit/sembol seçenekleri tekrarlanabilir. `--explain` dahil edilen özetlerin puan ve eşleşme nedenlerini yazar. Görev/dosya/sembol/commit geçerliliği ve kapsamın tüm summary iddialarına otomatik bağlanması henüz yapılmıyor. Girdi verilmezse önceki yenilik tabanlı seçim ve kronolojik çıktı korunur. `--kopyala` bir Git deposuna yazacaksa hedef dosyanın izlenmemesi ve hedef deponun `.gitignore` kurallarıyla dışlanması gerekir; aksi hâlde kopya durdurulur.
Kaynak tur aralıkları bilinen Bölüm/Cilt adaylarında, daha üst sıralı özetler aynı oturumdaki bir adayın tüm aralığını kapsıyorsa aday dışarıda bırakılır ve `--explain` nedenini gösterir. Kısmi çakışan aralıklar benzersiz bilgi kaybolmasın diye birlikte tutulur; manuel düzenlenen veya provenance'i eksik adaylar otomatik elenmez. Retrieval değerlendirmesi atıfsız adayların sayısını overlap filtrelemesinden önce ve sonra ayrı raporlar. Sentetik kısmi çakışma örneği 10 tekil turun tamamının korunduğunu, ancak 2 tur kapsamının tekrarlandığını gösterir. Bu sonuç gerçek arşiv kalitesini temsil etmez; temsil gücü olan bağımsız etiketli veride tekrar ve bilgi kaybını ölçmek açık iştir.

Geliştirici regresyonlarını `python scripts/evaluate_retrieval.py`, `python scripts/evaluate_context_generation.py` ve `python scripts/evaluate_provenance.py` ile çalıştırabilirsiniz. Provenance değerlendirmesi sentetik, elle etiketli bir Codex kaydıyla olay/tur atfını, desteklenen/desteklenmeyen özet iddialarını ve Git çalışma ağacıyla eşleşen test kanıtını ölçer; gerçek özetlerin doğruluğu veya temsilî kaynak/commit atfı hakkında kanıt sayılmaz.

## Güvenlik ve sınırlar

- Bu klonda commit öncesi korumayı kurmak için `python scripts/install_hook.py` çalıştırın. Kurulum var olan `pre-commit` hook'unu yedekleyip korur. Koruma Git index'ine seçilmiş dosyaları tarar; kişisel arşiv/ayar yollarını, yaygın sır kalıplarını ve tam kullanıcı ev yollarını engeller. Bu, bilinmeyen sırları yakalama garantisi değildir ve `git commit --no-verify` ile atlanabilir.
- `raw/` sohbet metni ve olası sırlar içerir. Arşivi, `ctxzip.settings.json` ayar dosyasını ve `BAGLAM.md` çıktısını açık depoya koymayın. Eski `ctxzip_ayar.json` dosyaları da otomatik yüklenir.
- Döküm ve model isteminde bilinen anahtar kalıpları maskelenir; bu eksiksiz bir sır taraması değildir. Otomatik özetlemede metin seçilen sağlayıcıya gönderilir; `--elle` otomatik ağ çağrısı yapmaz.
- Token hesabı yaklaşık `karakter/3.5` değeridir. Varsayılan `priority` profili mevcut ortak bütçeyi korur. İsteğe bağlı `--budget-profile balanced`, görev/durum, kararlar, Git/test, dosyalar ve özetler için ayrı oranlı tavanlar uygular; ham kaynak turlarından geçerli Bölüm aralıklarının dışındaki en yeni 20 turu ayrılmış bütçeye ekler ve güvenlik payını ayrı tutar.
- Antigravity için yalnızca bulunan `brain/<id>/*.md` dosyaları alınır. Bulut oturumları kendiliğinden yerel arşive gelmez. Dışa aktarımlar hassas hesap verileri içerebilir; yalnızca gereken dosyayı yerel `gelen/` klasörüne koyun ve arşivi Git dışında tutun. ChatGPT ZIP'i otomatik açılmaz.

## Geliştirme doğrulaması

`python -m unittest discover -s tests -v` ve `python ctxzip.py --help` çalıştırın. Task-aware selector değerlendirmesini `python scripts/evaluate_retrieval.py` ile yenilik sırasına karşı; üretim context akışını `python scripts/evaluate_context_generation.py` ile sentetik projede çalıştırabilirsiniz. Sentetik retrieval ve overlap aşamalarını `python scripts/benchmark_retrieval.py` ile farklı aday sayılarında ölçebilirsiniz; bu ölçüm disk I/O'sunu veya gerçek arşiv dağılımını modellemez. Üretim değerlendirmesi gerçek `build_context_pack` yolunda değişmiş kaynaklı Bölüm/Cilt elemesini, kaynak aralığı atfı olmayan eski bir özetin korunmasını, kaynaklı karar seçimini, ilgisiz büyük kaydın bütçeden çıkarılmasını, Git manifestini, çıktıdaki API anahtarı temizliğini ve token sınırını birlikte denetler. Testler kişisel verisi temizlenmiş Claude Code/Codex temel JSONL örneklerini, sentetik Claude/Codex araç yoğun fixture'larını ve normalize olay goldens'larını denetler. Araç yoğun örnekler parser dallarını kapsar; yeni upstream şema sürümlerini doğrulamaz. Fixture'lar az sayıda kaynak biçimi sürümünü kapsar; retrieval seti küçüktür ve tamamen temsili değildir. Bu değerlendirmeler genel kalite iddiası veya ağırlık ayarı için benchmark sayılmaz; gerçek LLM sağlayıcı bağlantısını doğrulamaz.

## Belgeler

[Ajan kılavuzu](AGENTS.md) · [Mimari](ARCHITECTURE.md) · [Karar kayıtları](docs/adr/README.md) · [Katkı kılavuzu](CONTRIBUTING.md) · [Yol haritası](ROADMAP.md) · [Plan](docs/PLAN.md) · [Görevler](docs/TASKS.md) · [Teknik bilgi](docs/KNOWLEDGE.md) · [Değişiklikler](CHANGELOG.md)

## Lisans

[GPL-3.0](LICENSE) © Halil Emre
