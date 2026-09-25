# Mimari

CtxZip, Python 3.10+ standart kütüphanesi kullanan bir CLI uygulamasıdır. `ctxzip.py` komutları ve veri akışını yönetir; güvenlik ve dış dünya sınırları `ctxzip_core/` modüllerindedir.

```text
kaynak tarayıcıları → topla → raw/
raw/ → biçim ayrıştırıcıları → dokum/
turlar → ozetle → bolumler/ → ciltler/
bolumler/ + ciltler/ → baglam → BAGLAM.md
```

| Katman | Rolü | Sınırı |
| --- | --- | --- |
| `raw/` | Kaynak kopyası | Oturum büyüdükçe güncellenir. Kaynak küçülürse önceki kopya ayrıca saklanır. Gizli veri içerebilir. |
| `dokum/` | Okunabilir Markdown | Araç çıktıları kısaltılır; ham kaydın yerini almaz. |
| `bolumler/` | Tek oturumun tur aralıkları | Kaynak turu ve hash üst verisi vardır; özet yanlış olabilir. |
| `ciltler/` | Dolu Bölümlerin üst özeti | Ayrıntı kaybı artar. |
| `durum.json` | İşlenmiş aralıklar ve Bölüm/Cilt ilişkileri | İşlem durumudur, sohbet kaynağı değildir. |
| `BAGLAM.md` | Yeni sohbet paketi | Kod, Git ve testin yerine geçmez. |

Kod haritası: `ctxzip.py` içindeki `kaynaklari_bul/topla` kaynakları kopyalar; `claude_turlari/codex_turlari/antigravity_turlari/elle_turlari` kaydı `Tur` nesnelerine çevirir; `dokum_yaz` okunabilir metin oluşturur; `ozetle/cilt_katla` özetleri düzenler; `baglam` doldurulmuş özetleri seçer. `ctxzip_core/privacy.py` maskeleme, `ctxzip_core/llm.py` önizleme/onay/ağ çağrısı, `ctxzip_core/git_safety.py` hedef deponun ignore kontrolünden sorumludur.

Bağımlılık yönü: `ctxzip.py → ctxzip_core`; `llm.py → privacy.py`. Çekirdek modüller CLI dosyasını içe aktarmaz. Yeni kaynak ayrıştırıcıları ve özetleme durum yönetimi bu sınırlara göre ayrılmalıdır; modüller arasında döngü kurulmaz.

Bir Bölüm oturum sınırını aşmaz. Aktif oturumun son parçası bekletilir. Doldurulmamış Bölüm Cilt'e veya bağlam paketine girmez. Özet, kaynak kaydın ve güncel projenin yerine geçmez.

Başlıca mimari borç: kaynak ayrıştırıcıları ve özetleme durum yönetimi hâlâ `ctxzip.py` içinde; biçim değişiklikleri için test kapsamı, atomik yazma ve görevle ilgili özet seçimi eksik. Bunları davranışı koruyan küçük adımlarla ayırma hedefi [görevlerde](docs/TASKS.md).

Gönderim sınırı: `llm_cagir` bilinen sır kalıplarını temizler, isteğin tam metnini ve hedefini önizler; etkileşimli onay veya açık `--onayli-gonder` olmadan ağ isteği yapmaz. Git sınırı: `baglam --kopyala` hedef depoda dosyanın izlenmemesini ve ignore edilmesini ister; `scripts/check_staged.py` seçilmiş index içeriğini tarar; `scripts/install_hook.py` mevcut `pre-commit` hook'unu koruyarak denetimi ekler. Bunlar kapsamlı veri kaybı önleme sistemi değildir.
