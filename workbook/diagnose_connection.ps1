param([string]$Database,[switch]$EnvironmentOnly)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$report=[ordered]@{protocol=2;ok=$false;code='UNKNOWN';bits=([IntPtr]::Size*8);provider='';phase='environment';native_errors=@();hresult='';office_platform='';office_msi=$false;attempts=@()}
$connection=$null
function Classify($phase,$native,$hr,$description) {
 if($phase -eq 'schema'){return 'SCHEMA_MISMATCH'}
 # Local matching only: ACE native error numbers vary between installations.
 # Descriptions may contain paths; never include them in the report.
 if($description -match '(?i)unrecognized database format|not a valid database|database.*corrupt|無法辨識.{0,8}資料庫|無法識別.{0,8}資料庫|不是有效的資料庫|資料庫.*損毀'){return 'FORMAT_INVALID'}
 if($description -match '(?i)not a valid password|invalid password|需要密碼|密碼無效|密碼不正確'){return 'PASSWORD_REQUIRED'}
 if($description -match '(?i)opened exclusively|exclusively locked|已.*獨占|已.*獨佔'){return 'DATABASE_LOCKED'}
 if($native -contains 3031){return 'PASSWORD_REQUIRED'}
 if(($native -contains 3049) -or ($native -contains 3343)){return 'FORMAT_INVALID'}
 if(($native -contains 3051) -or ($native -contains 3033) -or ($hr -eq '0x80070005')){return 'ACCESS_DENIED'}
 if(($native -contains 3045) -or ($native -contains 3260) -or ($native -contains 3188)){return 'DATABASE_LOCKED'}
 if(($native -contains 3024) -or ($native -contains 3044)){return 'FILE_NOT_FOUND'}
 if($hr -eq '0x800A0E7A'){return 'NO_PROVIDER'}
 return 'OPEN_FAILED'
}
try {
 # Only installation flags, no paths, product IDs, or exception descriptions.
 foreach($view in @([Microsoft.Win32.RegistryView]::Registry64,[Microsoft.Win32.RegistryView]::Registry32)) {
  $base=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine,$view)
  try {
   $key=$base.OpenSubKey('SOFTWARE\Microsoft\Office\ClickToRun\Configuration')
   if($key){try{$platform=[string]$key.GetValue('Platform');if($platform -in @('x86','x64')){$report.office_platform=$platform}}finally{$key.Dispose()}}
   $uninstall=$base.OpenSubKey('SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall')
   if($uninstall){try{foreach($name in $uninstall.GetSubKeyNames()){
    $key=$uninstall.OpenSubKey($name)
    if($key){try{if(($key.GetValue('WindowsInstaller') -eq 1) -and ([string]$key.GetValue('DisplayName') -match '^Microsoft (Office|Access|365)')){$report.office_msi=$true}}finally{$key.Dispose()}}
   }}finally{$uninstall.Dispose()}}
  }finally{$base.Dispose()}
 }
 if($EnvironmentOnly){$report.ok=$true;$report.code='ENVIRONMENT';return}
 $report.phase='file'
 if(-not [System.IO.File]::Exists($Database)){$report.code='FILE_NOT_FOUND';return}
 $stream=[System.IO.File]::Open($Database,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::ReadWrite)
 $stream.Dispose();$available=$false
 foreach($provider in @('Microsoft.ACE.OLEDB.12.0','Microsoft.ACE.OLEDB.16.0')){
  $report.phase='provider'
  if(-not [Type]::GetTypeFromProgID($provider)){continue}
  $available=$true;$report.provider=$provider;$connection=$null
  try {
   $connection=New-Object -ComObject ADODB.Connection
   $builder=New-Object System.Data.OleDb.OleDbConnectionStringBuilder
   $builder['Provider']=$provider;$builder['Data Source']=[IO.Path]::GetFullPath($Database);$builder['Mode']='Read'
   $report.phase='open';$connection.Open($builder.ConnectionString)
   $report.phase='schema'
   # WHERE 1=0 validates fields without retrieving patient values.
   foreach($sql in @(
    'SELECT LCHK_ID,LCHK_DEPT,LCHK_SOURCE,LCHK_INDATE,LCHK_OPDDATE,LCHK_WORKNO,LCHK_PATNAME,LCHK_SEX,LCHK_PATID,LCHK_PATKEY,LCHK_SMEMO1,LCHK_SMEMO2,LCHK_RMEMO1,LCHK_RMEMO2 FROM LCHKDATA WHERE 1=0',
    'SELECT LCHK_ID,LCHK_ITEM,LCHK_ITEMTYPE,LCHK_ITEMSER,LCHK_MKEY FROM LCHKDATA2 WHERE 1=0',
    'SELECT LCI_ID,LCI_NAME,LCI_NAMEC,LCI_NAMES,LCI_NHICODE FROM LCHKITEM WHERE 1=0',
    'SELECT HOS_ID,HOS_NAME FROM LHOSPITAL WHERE 1=0',
    'SELECT LCS_ID,LCS_NAME,LCS_NHICODE,LCS_HOSPITAL,LCS_UNIKEY FROM LCHKSET1 WHERE 1=0',
    'SELECT LCS_UNIKEY,LCS_ITEM,LCS_SERIAL FROM LCHKSET2 WHERE 1=0',
    'SELECT LCHK_ID,LCHK_CARD FROM LCHKNHI WHERE 1=0',
    'SELECT LPAT_PATKEY,LPAT_REMARK FROM LPATIENT WHERE 1=0'
   )){$recordset=$connection.Execute($sql);$recordset.Close()}
   $report.ok=$true;$report.code='OK';$report.native_errors=@();$report.hresult='';break
  } catch {
   $native=@();$description='';if($connection){try{foreach($e in $connection.Errors){$native+=([int]$e.NativeError);$description+=' '+[string]$e.Description}}catch{}}
   $cause=$_.Exception;while($cause.InnerException){$cause=$cause.InnerException}
   $hr='0x'+$cause.HResult.ToString('X8')
   $report.native_errors=@($native|Select-Object -Unique);$report.hresult=$hr
   $report.code=Classify $report.phase $native $hr $description
   $report.attempts+=@{provider=$provider;phase=$report.phase;code=$report.code;native_errors=$report.native_errors;hresult=$hr}
   if($report.code -in @('SCHEMA_MISMATCH','PASSWORD_REQUIRED','FORMAT_INVALID','FILE_NOT_FOUND','ACCESS_DENIED','DATABASE_LOCKED')){break}
  } finally {if($connection -and $connection.State -ne 0){try{$connection.Close()}catch{}}}
 }
 if(-not $available){$report.code='NO_PROVIDER'}
} catch {
 $cause=$_.Exception;while($cause.InnerException){$cause=$cause.InnerException}
 $report.hresult='0x'+$cause.HResult.ToString('X8')
 if($cause -is [UnauthorizedAccessException]){$report.code='ACCESS_DENIED'}
 elseif($report.phase -eq 'file'){$report.code='FILE_UNREADABLE'}
 else{$report.code='ENVIRONMENT_FAILED'}
} finally {$report|ConvertTo-Json -Depth 6 -Compress}
