# VIKKY uploader matrix

|Provider|Interface|Large-file method|Auth|
|---|---|---|---|
|Cloudflare R2|S3-compatible|multipart/resumable|credentials|
|Backblaze B2|S3/native|large/multipart|credentials|
|Wasabi|S3-compatible|multipart|credentials|
|Google Drive|Drive API|resumable|OAuth|
|Microsoft OneDrive|Microsoft Graph|resumable|OAuth|
|Amazon S3|S3 API|multipart|credentials|
|Azure Blob|Azure API/SDK|block upload|credentials|
|Google Cloud Storage|GCS API|resumable|credentials|
|DigitalOcean Spaces|S3-compatible|multipart|credentials|
|Cloudinary|Cloudinary API|provider-specific|credentials|
|Pixeldrain|Pixeldrain API|provider/account limits|auth|
|Dropbox|Dropbox API|upload sessions|OAuth|
|Box|Box API|chunked upload|OAuth|
|pCloud|pCloud API|provider-specific|auth|
|Filebase|S3/IPFS|multipart|credentials|

No provider is promised unlimited/free/permanent/API-free access. Private accounts require authorization.
