param([Parameter(Mandatory=$true)][string]$Database,
      [Parameter(Mandatory=$true)][datetime]$Date,
      [Parameter(Mandatory=$true)][string]$Output,
      [switch]$IncludeIdentity,
      [ValidateSet('Microsoft.ACE.OLEDB.12.0','Microsoft.ACE.OLEDB.16.0')][string]$Provider='Microsoft.ACE.OLEDB.12.0')
$ErrorActionPreference='Stop'
if([Threading.Thread]::CurrentThread.GetApartmentState() -ne 'MTA'){
 $bridgeShell=(Get-Process -Id $PID).Path
 $bridgeArgs=@('-NoProfile','-NonInteractive','-Mta','-ExecutionPolicy','Bypass','-File',$PSCommandPath,
               '-Database',$Database,'-Date',$Date.ToString('yyyy-MM-dd',[cultureinfo]::InvariantCulture),'-Output',$Output,'-Provider',$Provider)
 if($IncludeIdentity){$bridgeArgs+='-IncludeIdentity'}
 & $bridgeShell @bridgeArgs
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
      $f=$r.Fields.Item($i);$v=$f.Value;if($v -is [DBNull]){$v=$null};if($v -is [datetime]){$v=$v.ToString('yyyy-MM-ddTHH:mm:ss',[cultureinfo]::InvariantCulture)};$row[$f.Name]=$v
    }
    $list.Add([pscustomobject]$row);$r.MoveNext()
  }}finally{$r.Close()}
  return ,$list.ToArray()
}
try{
 $c.Open($b.ConnectionString)
 $start=$Date.Date.ToString('MM/dd/yyyy',[cultureinfo]::InvariantCulture)
 $end=$Date.Date.AddDays(1).ToString('MM/dd/yyyy',[cultureinfo]::InvariantCulture)
 $where="h.LCHK_INDATE >= #$start# AND h.LCHK_INDATE < #$end#"
 # Explicit local-only name / sex / chart number. Never return raw free text, card or ID values.
 $identity='';$headerFrom='LCHKDATA AS h'
 if($IncludeIdentity){
  $headerFrom='LCHKDATA AS h LEFT JOIN LPATIENT AS p ON h.LCHK_PATKEY=p.LPAT_PATKEY'
  $memo="(h.LCHK_SMEMO1 & ' ' & h.LCHK_SMEMO2 & ' ' & h.LCHK_RMEMO1 & ' ' & h.LCHK_RMEMO2 & ' ' & p.LPAT_REMARK)"
  $insurance="IIf(InStr(1,$memo,'保險')>0,'保險','')"
  foreach($label in @('新光','國泰','南山','富邦','台灣人壽','中國人壽','三商美邦','遠雄','全球人壽')){
   $insurance="IIf(InStr(1,$memo,'$label')>0,'$label',$insurance)"
  }
  # User explicitly confirmed LCHK_PATID as chart number. Local file only, never stdout.
  $identity=",h.LCHK_PATNAME,h.LCHK_SEX,h.LCHK_PATID AS CHART_NUMBER,$insurance AS INSURANCE_LABEL"
 }
 $headers=Rows "SELECT h.LCHK_DEPT,h.LCHK_WORKNO,h.LCHK_SOURCE,h.LCHK_INDATE,h.LCHK_OPDDATE$identity FROM $headerFrom WHERE $where ORDER BY h.LCHK_DEPT,h.LCHK_WORKNO"
 $details=Rows "SELECT h.LCHK_DEPT,h.LCHK_WORKNO,d.LCHK_ITEM,d.LCHK_ITEMTYPE,d.LCHK_ITEMSER FROM LCHKDATA AS h INNER JOIN LCHKDATA2 AS d ON h.LCHK_ID=d.LCHK_ID WHERE $where ORDER BY h.LCHK_DEPT,h.LCHK_WORKNO,d.LCHK_ITEMSER"
 $items=Rows 'SELECT LCI_ID,LCI_NAME,LCI_NAMEC,LCI_NAMES FROM LCHKITEM'
 $hospitals=Rows 'SELECT HOS_ID,HOS_NAME FROM LHOSPITAL'
 $sets=Rows 'SELECT LCS_ID,LCS_NAME,LCS_UNIKEY,LCS_HOSPITAL FROM LCHKSET1'
 $setMembers=Rows 'SELECT LCS_UNIKEY,LCS_ITEM,LCS_SERIAL FROM LCHKSET2'
 # Only return positive work-number flags, never the raw card value.
 $adultHealth=Rows "SELECT DISTINCT h.LCHK_DEPT,h.LCHK_WORKNO FROM LCHKDATA AS h INNER JOIN LCHKNHI AS n ON h.LCHK_ID=n.LCHK_ID WHERE $where AND UCase(Left(Trim(n.LCHK_CARD),2))='IC'"
 $package=[ordered]@{date=$Date.ToString('yyyy-MM-dd');headers=$headers;details=$details;items=$items;hospitals=$hospitals;sets=$sets;set_members=$setMembers;adult_health=$adultHealth;identity_local_only=[bool]$IncludeIdentity;chart_number_source='LCHKDATA.LCHK_PATID'}
 $package | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -LiteralPath $Output
} catch {
 # Do not echo exception objects or patient records.
 [Console]::Error.WriteLine('Access read failed. Check file, ACE provider and file permissions.'); exit 1
} finally {if($c.State -ne 0){$c.Close()}}
