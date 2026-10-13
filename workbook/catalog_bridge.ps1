param([string]$Database,[string]$Output,[ValidateSet('Microsoft.ACE.OLEDB.12.0','Microsoft.ACE.OLEDB.16.0')][string]$Provider='Microsoft.ACE.OLEDB.12.0')
$ErrorActionPreference='Stop'
if([Threading.Thread]::CurrentThread.GetApartmentState() -ne 'MTA'){
 $bridgeShell=(Get-Process -Id $PID).Path
 & $bridgeShell -NoProfile -NonInteractive -Mta -ExecutionPolicy Bypass -File $PSCommandPath -Database $Database -Output $Output -Provider $Provider
 exit $LASTEXITCODE
}
$c=New-Object -ComObject ADODB.Connection
$b=New-Object System.Data.OleDb.OleDbConnectionStringBuilder
$b['Provider']=$Provider
$b['Data Source']=(Resolve-Path -LiteralPath $Database).Path
$b['Mode']='Read'
function Rows([string]$sql){
  $r=$c.Execute($sql); $list=[System.Collections.Generic.List[object]]::new()
  try {while(!$r.EOF){
    $row=[ordered]@{}
    for($i=0;$i -lt $r.Fields.Count;$i++){
      $f=$r.Fields.Item($i);$v=$f.Value;if($v -is [DBNull]){$v=$null};$row[$f.Name]=$v
    }
    $list.Add([pscustomobject]$row);$r.MoveNext()
  }}finally{$r.Close()}
  return ,$list.ToArray()
}
try {
 $c.Open($b.ConnectionString)
 $items=Rows 'SELECT LCI_ID,LCI_NAME,LCI_NAMEC,LCI_NAMES,LCI_NHICODE FROM LCHKITEM'
 $sets=Rows 'SELECT LCS_ID,LCS_NAME,LCS_NHICODE,LCS_HOSPITAL,LCS_UNIKEY FROM LCHKSET1'
 $members=Rows 'SELECT LCS_UNIKEY,LCS_ITEM,LCS_SERIAL FROM LCHKSET2'
 $hospitals=Rows 'SELECT HOS_ID,HOS_NAME FROM LHOSPITAL'
 @{items=$items;sets=$sets;hospitals=$hospitals;set_members=$members} | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 -LiteralPath $Output
} catch { [Console]::Error.WriteLine('Catalog read failed.');exit 1 }
finally {if($c.State -ne 0){$c.Close()}}
