# Mimari

CtxZip, Python 3.10+ standart kütüphanesi kullanan tek dosyalı bir CLI uygulamasıdır: `ctxzip.py`.

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

Kod haritası: `kaynaklari_bul/topla` kaynakları kopyalar; `claude_turlari/codex_turlari/antigravity_turlari/elle_turlari` kaydı `Tur` nesnelerine çevirir; `dokum_yaz` okunabilir metin oluşturur; `ozetle/cilt_katla/llm_cagir` özetler; `baglam` doldurulmuş özetleri en yeniden başlayarak yaklaşık token bütçesine seçer.

Bir Bölüm oturum sınırını aşmaz. Aktif oturumun son parçası bekletilir. Doldurulmamış Bölüm Cilt'e veya bağlam paketine girmez. Özet, kaynak kaydın ve güncel projenin yerine geçmez.

Başlıca mimari borç: tek dosyada çok sorumluluk, biçim değişiklikleri için yetersiz regresyon testleri, atomik yazma eksikliği ve görevle ilgili özetleri seçememe. Ayrıntılar [görevlerde](docs/TASKS.md).
