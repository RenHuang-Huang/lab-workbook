param([Parameter(Mandatory=$true)][string]$Database)
$ErrorActionPreference='Stop'
# ACE/Office cleanup can crash in a windowless STA host. Also protects older EXEs.
if([Threading.Thread]::CurrentThread.GetApartmentState() -ne 'MTA'){
 $bridgeShell=(Get-Process -Id $PID).Path
 & $bridgeShell -NoProfile -NonInteractive -Mta -ExecutionPolicy Bypass -File $PSCommandPath -Database $Database
 exit $LASTEXITCODE
}
$connection=$null
try {
 $connection=New-Object -ComObject ADODB.Connection
 $builder=New-Object System.Data.OleDb.OleDbConnectionStringBuilder
 $builder['Provider']='Microsoft.ACE.OLEDB.12.0'
 $builder['Data Source']=(Resolve-Path -LiteralPath $Database).Path
 $builder['Mode']='Read'
 $connection.Open($builder.ConnectionString)
 # Validate required schema without retrieving any patient row or identifiers.
 foreach($sql in @(
  'SELECT LCHK_INDATE,LCHK_OPDDATE,LCHK_WORKNO FROM LCHKDATA WHERE 1=0',
  'SELECT LCHK_ITEM,LCHK_ITEMTYPE FROM LCHKDATA2 WHERE 1=0',
  'SELECT LCI_ID FROM LCHKITEM WHERE 1=0',
  'SELECT HOS_ID FROM LHOSPITAL WHERE 1=0',
  'SELECT LCS_ID FROM LCHKSET1 WHERE 1=0',
  'SELECT LCS_ITEM FROM LCHKSET2 WHERE 1=0',
  'SELECT LCHK_ID FROM LCHKNHI WHERE 1=0'
 )) {$recordset=$connection.Execute($sql);$recordset.Close()}
 Write-Output 'OK'
} catch {Write-Output 'FAILED';exit 1}
finally {if($connection -and $connection.State -ne 0){$connection.Close()}}
