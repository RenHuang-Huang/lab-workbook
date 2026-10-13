param([Parameter(Mandatory=$true)][string]$Installer,[Parameter(Mandatory=$true)][string]$ExpectedHash,[switch]$VerifyOnly)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
try {
 if((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne $ExpectedHash){throw 'HASH'}
 $signature=Get-AuthenticodeSignature -LiteralPath $Installer
 if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|, )O=Microsoft Corporation(,|$)'){throw 'SIGNATURE'}
 if($VerifyOnly){@{code='VERIFIED'}|ConvertTo-Json -Compress;return}
 # Official interactive installer; Windows UAC and Microsoft terms stay visible.
 # Never pass /quiet, force-close applications, remove Office, or alter registry permissions.
 $process=Start-Process -FilePath $Installer -Verb RunAs -PassThru -Wait
 @{code='INSTALLER_EXIT';exit_code=$process.ExitCode}|ConvertTo-Json -Compress
} catch {
 $cause=$_.Exception;while($cause.InnerException){$cause=$cause.InnerException}
 $code='INSTALLER_FAILED'
 if($cause.Message -eq 'HASH' -or $cause.Message -eq 'SIGNATURE'){$code='INSTALLER_UNTRUSTED'}
 if($cause.NativeErrorCode -eq 1223 -or $cause.HResult -eq -2147023673){$code='INSTALLER_CANCELLED'}
 @{code=$code}|ConvertTo-Json -Compress
}
