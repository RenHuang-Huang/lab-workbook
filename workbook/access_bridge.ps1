param([Parameter(Mandatory=$true)][string]$Database,
      [Parameter(Mandatory=$true)][datetime]$Date,
      [Parameter(Mandatory=$true)][string]$Output,
      [switch]$IncludeIdentity,
      [switch]$IncludeOrderNotes,
      [string]$CaseWorkNumber='',
      [switch]$UsageStatistics,
      [datetime]$StartDate,
      [ValidateSet('Microsoft.ACE.OLEDB.12.0','Microsoft.ACE.OLEDB.16.0')][string]$Provider='Microsoft.ACE.OLEDB.12.0')
$ErrorActionPreference='Stop'
if([Threading.Thread]::CurrentThread.GetApartmentState() -ne 'MTA'){
 $bridgeShell=(Get-Process -Id $PID).Path
 $bridgeArgs=@('-NoProfile','-NonInteractive','-Mta','-ExecutionPolicy','Bypass','-File',$PSCommandPath,
               '-Database',$Database,'-Date',$Date.ToString('yyyy-MM-dd',[cultureinfo]::InvariantCulture),'-Output',$Output,'-Provider',$Provider)
 if($IncludeIdentity){$bridgeArgs+='-IncludeIdentity'}
 if($IncludeOrderNotes){$bridgeArgs+='-IncludeOrderNotes'}
 if($CaseWorkNumber){$bridgeArgs+=@('-CaseWorkNumber',$CaseWorkNumber)}
 if($UsageStatistics){$bridgeArgs+=@('-UsageStatistics','-StartDate',$StartDate.ToString('yyyy-MM-dd',[cultureinfo]::InvariantCulture))}
 & $bridgeShell @bridgeArgs
 exit $LASTEXITCODE
}
$c=New-Object -ComObject ADODB.Connection
$b=New-Object System.Data.OleDb.OleDbConnectionStringBuilder
$b['Provider']=$Provider
$b['Data Source']=(Resolve-Path -LiteralPath $Database).Path
$b['Mode']='Read'
function Rows([string]$sql,[object[]]$parameters=@()){
  $command=New-Object -ComObject ADODB.Command
  $command.ActiveConnection=$c;$command.CommandText=$sql;$command.CommandTimeout=120
  foreach($value in $parameters){
    $parameter=$command.CreateParameter('',202,1,[Math]::Max(1,([string]$value).Length),[string]$value)
    $command.Parameters.Append($parameter)
  }
  $r=$command.Execute(); $list=[System.Collections.Generic.List[object]]::new()
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
 if($UsageStatistics){
  if($StartDate.Date -gt $Date.Date -or $StartDate.Year -lt 1900){throw 'Invalid period'}
  $usageStart=$StartDate.Date.ToString('MM/dd/yyyy',[cultureinfo]::InvariantCulture)
  $period="h.LCHK_INDATE >= #$usageStart# AND h.LCHK_INDATE < #$end#"
  $totals=@{};$unknown=0;$orders=0;$linkedRows=0;$unresolvedRows=0
  function ApplyOrder($entries,[string]$day){
   $script:orders++
   $panels=[System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
   foreach($entry in $entries){if($entry[0] -ceq 'G' -and $entry[1]){[void]$panels.Add($entry[1])}}
   $states=@{}
   foreach($entry in $entries){
    $kind=$entry[0];$code=$entry[1];$parent=$entry[2]
    if($kind -cnotin @('G','I') -or !$code){$script:unknown++;continue}
    $key=$kind+'|'+$code
    if(!$states.ContainsKey($key)){$states[$key]=@{kind=$kind;code=$code;direct=$false;uncertain=$false}}
    if($kind -ceq 'G' -or !$parent){$states[$key].direct=$true}
    elseif($panels.Contains($parent)){$script:linkedRows++}
    else{$states[$key].direct=$true;$states[$key].uncertain=$true;$script:unresolvedRows++}
   }
   foreach($key in $states.Keys){
    $state=$states[$key]
    if(!$totals.ContainsKey($key)){$totals[$key]=@{kind=$state.kind;code=$state.code;total_count=0;direct_count=0;uncertain_count=0;first_used=$day;last_used=$day;first_direct='';last_direct=''}}
    $item=$totals[$key];$item.total_count++
    if($day -clt $item.first_used){$item.first_used=$day};if($day -cgt $item.last_used){$item.last_used=$day}
    if($state.direct){
     $item.direct_count++
     if(!$item.first_direct -or $day -clt $item.first_direct){$item.first_direct=$day}
     if(!$item.last_direct -or $day -cgt $item.last_direct){$item.last_direct=$day}
    }
    if($state.uncertain){$item.uncertain_count++}
   }
  }
  # Chunk by calendar month and process one original order at a time. Internal
  # order IDs are only local grouping keys; the output contains aggregate counts.
  $cursor=$StartDate.Date;$until=$Date.Date.AddDays(1)
  while($cursor -lt $until){
   $next=[datetime]::new($cursor.Year,$cursor.Month,1).AddMonths(1);if($next -gt $until){$next=$until}
   $lower=$cursor.ToString('MM/dd/yyyy',[cultureinfo]::InvariantCulture);$upper=$next.ToString('MM/dd/yyyy',[cultureinfo]::InvariantCulture)
   $c.CommandTimeout=120
   $r=$c.Execute("SELECT h.LCHK_ID,h.LCHK_INDATE,d.LCHK_ITEMTYPE,d.LCHK_ITEM,d.LCHK_MKEY FROM LCHKDATA h INNER JOIN LCHKDATA2 d ON h.LCHK_ID=d.LCHK_ID WHERE h.LCHK_INDATE>=#$lower# AND h.LCHK_INDATE<#$upper# ORDER BY h.LCHK_ID")
   $order=$null;$day='';$entries=[System.Collections.Generic.List[object]]::new()
   try{while(!$r.EOF){
    $block=$r.GetRows(2048)
    for($i=0;$i -lt $block.GetLength(1);$i++){
     $key=[string]$block[0,$i]
     if($null -ne $order -and $key -cne $order){ApplyOrder $entries $day;$entries.Clear()}
     $order=$key;$day=([datetime]$block[1,$i]).ToString('yyyy-MM-dd')
     $entries.Add(@(([string]$block[2,$i]).Trim(),([string]$block[3,$i]).Trim(),([string]$block[4,$i]).Trim()))
    }
   }}finally{$r.Close()}
   if($null -ne $order){ApplyOrder $entries $day}
   $cursor=$next
  }
  $items=Rows 'SELECT LCI_ID,LCI_NAME,LCI_NAMEC,LCI_NAMES,LCI_NHICODE FROM LCHKITEM'
  $sets=Rows 'SELECT LCS_ID,LCS_NAME,LCS_UNIKEY,LCS_HOSPITAL,LCS_NHICODE FROM LCHKSET1'
  $setMembers=Rows 'SELECT LCS_UNIKEY,LCS_ITEM,LCS_SERIAL FROM LCHKSET2'
  $hospitals=Rows 'SELECT HOS_ID,HOS_NAME FROM LHOSPITAL'
  $package=@{usage_statistics=$true;start_date=$StartDate.ToString('yyyy-MM-dd');end_date=$Date.ToString('yyyy-MM-dd');counts=@($totals.Values);order_count=$orders;unknown_detail_count=$unknown;linked_detail_count=$linkedRows;unresolved_detail_count=$unresolvedRows;catalog=@{items=$items;sets=$sets;set_members=$setMembers;hospitals=$hospitals}}
  $package | ConvertTo-Json -Depth 9 | Set-Content -Encoding utf8 -LiteralPath $Output
 }elseif($CaseWorkNumber){
  # Keep daily matching keys local. Return only matched orders and possible peers;
  # Python applies the same merge exclusions as the workbook. No patient table,
  # raw card, ID, memo, reference ranges or historical results are queried here.
  function WorkNumber([string]$value){
    $value=$value.Trim()
    if($value -cmatch '^[0-9]+$'){$value=$value.TrimStart('0');if(!$value){$value='0'}}
    return $value
  }
  $daily=Rows "SELECT h.LCHK_DEPT,h.LCHK_WORKNO,h.LCHK_SOURCE,h.LCHK_INDATE,h.LCHK_OPDDATE,h.LCHK_PATNAME,h.LCHK_SEX,h.LCHK_PATID AS CHART_NUMBER FROM LCHKDATA AS h WHERE $where ORDER BY h.LCHK_DEPT,h.LCHK_WORKNO"
  $needle=WorkNumber $CaseWorkNumber
  $matches=@($daily | Where-Object {(WorkNumber $_.LCHK_WORKNO) -ceq $needle})
  $headers=@($daily | Where-Object {
    $candidate=$_;$keep=$false
    foreach($hit in $matches){
      $sameOrder=($candidate.LCHK_DEPT -ceq $hit.LCHK_DEPT -and $candidate.LCHK_WORKNO -ceq $hit.LCHK_WORKNO)
      $clinic=([string]$hit.LCHK_SOURCE).Trim();$chart=([string]$hit.CHART_NUMBER).Trim();$name=([string]$hit.LCHK_PATNAME).Trim()
      $samePatient=$clinic -and $chart -and $name -and
        (([string]$candidate.LCHK_SOURCE).Trim() -ceq $clinic) -and
        (([string]$candidate.CHART_NUMBER).Trim() -ceq $chart) -and
        (([string]$candidate.LCHK_PATNAME).Trim() -ceq $name)
      if($sameOrder -or $samePatient){$keep=$true;break}
    }
    $keep
  })
  $details=[System.Collections.Generic.List[object]]::new()
  foreach($header in $headers){
    $dept=[string]$header.LCHK_DEPT
    $sql="SELECT h.LCHK_DEPT,h.LCHK_WORKNO,d.LCHK_ITEM,d.LCHK_ITEMTYPE,d.LCHK_ITEMSER,d.LCHK_MKEY,d.LCHK_VALUE,d.LCHK_VALUE2,d.LCHK_VALUE3,d.LCHK_RESULT,d.LCHK_UNIT FROM LCHKDATA AS h INNER JOIN LCHKDATA2 AS d ON h.LCHK_ID=d.LCHK_ID WHERE $where AND (h.LCHK_DEPT=? OR (h.LCHK_DEPT IS NULL AND ?='')) AND h.LCHK_WORKNO=? ORDER BY d.LCHK_ITEMSER"
    foreach($detail in (Rows $sql @($dept,$dept,[string]$header.LCHK_WORKNO))){$details.Add($detail)}
  }
  $items=Rows 'SELECT LCI_ID,LCI_NAME,LCI_NAMEC,LCI_NAMES FROM LCHKITEM'
  $hospitals=Rows 'SELECT HOS_ID,HOS_NAME FROM LHOSPITAL'
  $sets=Rows 'SELECT LCS_ID,LCS_NAME,LCS_UNIKEY,LCS_HOSPITAL FROM LCHKSET1'
  $setMembers=Rows 'SELECT LCS_UNIKEY,LCS_ITEM,LCS_SERIAL FROM LCHKSET2'
  $package=[ordered]@{date=$Date.ToString('yyyy-MM-dd');headers=$headers;details=$details.ToArray();items=$items;hospitals=$hospitals;sets=$sets;set_members=$setMembers;identity_local_only=$true;lookup_only=$true}
  $package | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -LiteralPath $Output
 }else{
 # Explicit local-only name / sex / chart number. Never return card or national-ID values.
 # The separately requested order memo is returned only with IncludeOrderNotes, to a local file.
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
 $orderNote=''
 if($IncludeOrderNotes){$orderNote=',h.LCHK_SMEMO1 AS ORDER_NOTE'}
 $headers=Rows "SELECT h.LCHK_DEPT,h.LCHK_WORKNO,h.LCHK_SOURCE,h.LCHK_INDATE,h.LCHK_OPDDATE$identity$orderNote FROM $headerFrom WHERE $where ORDER BY h.LCHK_DEPT,h.LCHK_WORKNO"
 $details=Rows "SELECT h.LCHK_DEPT,h.LCHK_WORKNO,d.LCHK_ITEM,d.LCHK_ITEMTYPE,d.LCHK_ITEMSER,d.LCHK_MKEY FROM LCHKDATA AS h INNER JOIN LCHKDATA2 AS d ON h.LCHK_ID=d.LCHK_ID WHERE $where ORDER BY h.LCHK_DEPT,h.LCHK_WORKNO,d.LCHK_ITEMSER"
 $items=Rows 'SELECT LCI_ID,LCI_NAME,LCI_NAMEC,LCI_NAMES FROM LCHKITEM'
 $hospitals=Rows 'SELECT HOS_ID,HOS_NAME FROM LHOSPITAL'
 $sets=Rows 'SELECT LCS_ID,LCS_NAME,LCS_UNIKEY,LCS_HOSPITAL FROM LCHKSET1'
 $setMembers=Rows 'SELECT LCS_UNIKEY,LCS_ITEM,LCS_SERIAL FROM LCHKSET2'
 # Only return positive work-number flags, never the raw card value.
 $adultHealth=Rows "SELECT DISTINCT h.LCHK_DEPT,h.LCHK_WORKNO FROM LCHKDATA AS h INNER JOIN LCHKNHI AS n ON h.LCHK_ID=n.LCHK_ID WHERE $where AND UCase(Left(Trim(n.LCHK_CARD),2))='IC'"
 $package=[ordered]@{date=$Date.ToString('yyyy-MM-dd');headers=$headers;details=$details;items=$items;hospitals=$hospitals;sets=$sets;set_members=$setMembers;adult_health=$adultHealth;identity_local_only=[bool]$IncludeIdentity;chart_number_source='LCHKDATA.LCHK_PATID';order_notes_included=[bool]$IncludeOrderNotes;order_notes_source=$(if($IncludeOrderNotes){'LCHKDATA.LCHK_SMEMO1'}else{''})}
 $package | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 -LiteralPath $Output
 }
} catch {
 # Do not echo exception objects or patient records.
 [Console]::Error.WriteLine('Access read failed. Check file, ACE provider and file permissions.'); exit 1
} finally {if($c.State -ne 0){$c.Close()}}
