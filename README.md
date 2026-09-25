# CtxZip

**Ctx** (context, bağlam) + **Zip** (sıkıştırma): AI kodlama ajanlarının uzayan sohbetlerini
kaybetmeden sıkıştırır.

Claude Code, Codex ve Antigravity sohbetlerini **proje bazında arşivler** ve Isekai Zero'daki gibi
**kademeli özetler**: oturumlar → **Bölüm** özetleri → birkaç bölüm dolunca **Cilt** özeti.
Yeni sohbete başlarken tek komutla **bağlam paketi** (`BAGLAM.md`) üretir.

Yalnızca Python 3.10+ standart kütüphanesini kullanır; `pip install` gerekmez.
Herhangi bir projeye veya editöre bağlı değildir; masaüstündeki ve buluttaki ajanlarla çalışır.

## Klasör yapısı

```
CtxZip-Arsiv/
└── Godot-AI-Sidebar/
    ├── raw/claude-code/*.jsonl    değişmez ham kayıt (kaynak silinse de burada kalır)
    ├── raw/codex/*.jsonl
    ├── raw/antigravity/<id>/*.md
    ├── gelen/                     elle eklenen sohbetler (.md / .txt: ChatGPT, web vb.)
    ├── dokum/*.md                 okunabilir döküm (araç çıktıları atılır, ham kayda işaret edilir)
    ├── bolumler/B0001.md …        bölüm özetleri — ELLE DÜZELTİLEBİLİR
    ├── ciltler/C001.md …          cilt özetleri — ELLE DÜZELTİLEBİLİR
    ├── durum.json                 hangi turun hangi bölümde olduğu
    └── BAGLAM.md                  yeni sohbete verilecek paket
```

Isekai'den farkları (Isekai Zero tekniği PDF'inin önerileri):

| Isekai | CtxZip | Neden |
|---|---|---|
| Her 20 mesajda bir bölüm | **Token bütçesiyle** bölüm (`bolum_token`, varsayılan ~25k) | Kodlamada tek bir tur 20 mesajdan büyük olabilir |
| Bölüm oturumlar arasında akabilir | Bölüm **bir oturumu asla aşmaz** | Oturum sonu doğal bir olay sınırı |
| — | Aktif oturumun son parçası, oturum kapanana kadar (`aktif_oturum_dk`) bekler | Yarım işi özetlememek için |
| 10 bölüm = 1 cilt | `cilt_bolum_sayisi` (varsayılan 8) | Ayarlanabilir |
| Özet düzenlenebilir | Aynı. Düzenlediğin özet **asla ezilmez**; ciltler senin düzeltmeni kullanır | Özet gerçeğin kaynağı değildir |
| Serbest metin özet | Sabit başlıklı özet: kararlar **[T12] kaynaklı**, test durumu **SHA ile**, "geçersizleşen bilgiler" ayrı | Eski "testler geçiyor" bilgisi yıllar sonra geri gelmesin |

## Kurulum (Windows)

1. Repoyu klonla veya bu klasörü örneğin `C:\Users\Halil Emre\Documents\CtxZip\` içine koy.
2. `ctxzip_ayar.ornek.json` dosyasını **`ctxzip_ayar.json`** adıyla kopyala ve düzenle:
   - `llm.model`: 9Router'da kullandığın model adı (9Router `http://127.0.0.1:20128/v1`).
   - `proje_takma_adlari`: farklı klasör adlarını tek projede toplamak için.
   - `haric_projeler`: ev klasöründe açtığın geçici oturumlar gibi arşivlenmeyecekler.
3. 9Router anahtar istiyorsa **koda yazma**, ortam değişkeni olarak ver:
   ```powershell
   [Environment]::SetEnvironmentVariable("CTXZIP_API_KEY", "<anahtar>", "User")
   ```

## Kullanım

```powershell
cd "C:\Users\Halil Emre\Documents\CtxZip"

python ctxzip.py topla                 # tüm araçlardaki oturumları arşive kopyala
python ctxzip.py dokum                 # okunabilir dökümleri üret
python ctxzip.py ozetle                # yeni turlardan bölüm, dolan bölümlerden cilt
python ctxzip.py hepsi                 # üçü birden
python ctxzip.py durum                 # projeler, bölüm/cilt sayıları, bekleyen/düzeltilen özetler

# Yeni sohbete başlarken: ~12k tokenlık paket, proje klasörüne kopyala
python ctxzip.py baglam Godot-AI-Sidebar --token 12000 --kopyala "C:\Users\Halil Emre\Desktop\GitHub\Public\Godot AI Sidebar"
```

Yeni sohbette ajana: **"AGENTS.md'yi ve BAGLAM.md'yi oku, kaldığımız yerden devam et."**
(`BAGLAM.md`'yi projede tutacaksan `.gitignore`'a ekle; özetler sohbet içeriği taşır.)

### LLM olmadan (elle mod)

```powershell
python ctxzip.py ozetle --elle
```
Her bölüm için `bolumler/B0007.istem.md` üretilir. İçeriğini Claude/ChatGPT/Gemini'ye yapıştır,
yanıtı `B0007.md` içindeki `<!-- BURAYA-YAPISTIR -->` satırının yerine koy. Sonradan
`llm.model` ayarlarsan `python ctxzip.py ozetle` bekleyenleri kendisi doldurur.

### Buluttaki oturumlar (claude.ai/code, Codex Cloud)

Bulut oturumları geçici bir sunucuda çalışır; kayıtları senin bilgisayarına gelmez ve sunucu
kapanınca silinir. Oturum bitmeden ajana şunu yaz:

> "Bu oturumun ham transcript dosyasını (Claude Code: `~/.claude/projects/<klasör>/<oturum>.jsonl`) bana dosya olarak gönder."

İndirdiğin `.jsonl` dosyasını `CtxZip-Arsiv/<proje>/gelen/` içine koy; araç Claude Code mu Codex mi
olduğunu içerikten anlar ve diğer oturumlar gibi dökümler/özetler.

### Otomatik çalıştırma (önerilir)

Araçlar eski oturumları bir süre sonra silebilir. **Bildiğim kadarıyla** Claude Code, eski oturum
dökümlerini varsayılan olarak ~30 gün sonra temizliyor (`cleanupPeriodDays` ayarı; güncel
değeri Claude Code belgelerinden kontrol et). Arşiv bu yüzden düzenli toplanmalı:

```powershell
$eylem = New-ScheduledTaskAction -Execute "python" -Argument "`"C:\Users\Halil Emre\Documents\CtxZip\ctxzip.py`" hepsi" -WorkingDirectory "C:\Users\Halil Emre\Documents\CtxZip"
$tetik = New-ScheduledTaskTrigger -Daily -At 23:30
Register-ScheduledTask -TaskName "CtxZip" -Action $eylem -Trigger $tetik -Description "AI sohbet arşivi + özet"
```

Ek güvence için Claude Code'da `~/.claude/settings.json` içine `"cleanupPeriodDays": 3650` yazılabilir.

## Güvenlik

- `raw/` **ham** kayıttır: sohbette geçen her şeyi (yapıştırılan anahtarlar dahil) içerir.
  Arşivi **public repoya koyma**. Yedek için özel (private) repo veya şifreli disk kullan.
- `dokum/` ve modele gönderilen metinden bilinen anahtar kalıpları (`sk-…`, `ghp_…`, `AKIA…`,
  `api_key=…` vb.) `[GİZLİ]` ile silinir. Bu bir **güvenlik ağıdır, garanti değildir**.
- Özetler 9Router üzerinden hangi sağlayıcıya gidiyorsa oraya gönderilir; hassas projelerde `--elle` kullan.

## Bilinen sınırlar (dürüst liste)

| Konu | Durum |
|---|---|
| Claude Code | Gerçek oturum dosyalarıyla test edildi (`~/.claude/projects/<klasör>/<oturum>.jsonl`). Alt-ajan (sidechain) mesajları atlanır. |
| Codex | Bilinen `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` formatına göre yazıldı, **gerçek bir Codex dosyasıyla test edilmedi**. Sorun olursa bir dosyanın ilk 5 satırını (gizli bilgileri silerek) paylaş. |
| Antigravity | Konuşmalar ikili formatta tutuluyor olabilir; araç yalnızca `~/.gemini/antigravity/brain/<id>/` altındaki **Markdown artefaktları** (task, plan, walkthrough) toplar. Bu yol **doğrulanmadı**; sende farklıysa `ctxzip_ayar.json`'da düzelt. Proje eşlemesi yok: hepsi `antigravity` projesine düşer, `proje_takma_adlari` ile konuşma kimliğini projeye eşleyebilirsin. Alternatif: sohbeti dışa aktar / kopyala → `gelen/` klasörüne `.md` olarak koy. |
| Token sayısı | Kaba tahmin (~3.5 karakter/token), gerçek tokenizer değil. |
| Özet kalitesi | Kullanılan modele bağlı. `durum` komutundaki **Düzeltilen** sütunu, elle düzelttiğin özet sayısını gösterir; yüksekse daha iyi bir özet modeli seç. |

## Lisans

[GPL-3.0](LICENSE) © Halil Emre
