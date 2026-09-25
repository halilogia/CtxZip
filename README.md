# CtxZip

**AI kodlama oturumlarını proje bazında arşivle, kademeli özetle ve yeni sohbete bağlam taşı.**

CtxZip, Claude Code ve Codex yerel oturumlarını, Antigravity'nin erişilebilen Markdown artefaktlarını toplar. Ham kayıtları saklar, okunabilir dökümler, **Bölüm** ve **Cilt** özetleri üretir. Yeni görev için token bütçeli `BAGLAM.md` hazırlar. Python 3.10+ standart kütüphanesi yeterlidir.

> **Durum:** Erken sürüm (`0.1.0`). Claude Code ve Codex yerel kayıtlarıyla içe aktarma denendi. Antigravity desteği tam sohbet geçmişini kapsamaz. Gerçek LLM ile özet kalitesi henüz doğrulanmadı.

## Hızlı başlangıç

```powershell
git clone https://github.com/halilogia/CtxZip.git
cd CtxZip
Copy-Item ctxzip_ayar.ornek.json ctxzip_ayar.json
# ctxzip_ayar.json içinde llm.model değerini kendi sağlayıcınızdaki model adıyla değiştirin.
python ctxzip.py hepsi
python ctxzip.py durum
python ctxzip.py baglam Proje-Adi --token 12000
```

LLM bağlantısı kurmadan ilerlemek için `python ctxzip.py hepsi --elle` çalıştırın. Oluşan `*.istem.md` dosyalarının yanıtlarını ilgili Bölüm dosyalarındaki `<!-- BURAYA-YAPISTIR -->` yerine koyun. Model adı boş veya örnek değerken otomatik özetleme çalıştırmayın.

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

`BAGLAM.md` eski oturumların özetidir. Güncel kod, Git durumu ve test sonuçlarıyla çelişirse onlar geçerlidir. `--kopyala` ile bir projeye koyarsanız o projenin `.gitignore` dosyasına `BAGLAM.md` ekleyin.

## Güvenlik ve sınırlar

- `raw/` sohbet metni ve olası sırlar içerir. Arşivi, `ctxzip_ayar.json` dosyasını ve `BAGLAM.md` çıktısını açık depoya koymayın.
- Döküm ve model isteminde bilinen anahtar kalıpları maskelenir; bu eksiksiz bir sır taraması değildir. Otomatik özetlemede metin seçilen sağlayıcıya gönderilir; `--elle` otomatik ağ çağrısı yapmaz.
- Token hesabı yaklaşık `karakter/3.5` değeridir. Bağlam seçimi şu an görev ilgisinden çok yeniliğe dayanır.
- Antigravity için yalnızca bulunan `brain/<id>/*.md` dosyaları alınır. Bulut oturumları kendiliğinden yerel arşive gelmez; dışa aktarılan kayıtlar ilgili projenin `gelen/` klasörüne konabilir.

## Belgeler

[Ajan kılavuzu](AGENTS.md) · [Mimari](ARCHITECTURE.md) · [Yol haritası](ROADMAP.md) · [Plan](docs/PLAN.md) · [Görevler](docs/TASKS.md) · [Teknik bilgi](docs/KNOWLEDGE.md) · [Değişiklikler](CHANGELOG.md)

## Lisans

[GPL-3.0](LICENSE) © Halil Emre
