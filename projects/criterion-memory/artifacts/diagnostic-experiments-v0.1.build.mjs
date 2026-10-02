import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root = '/Users/zhitaozhang/Documents/scholar';
const outputDir = `${root}/outputs/01a0f1e5-ff08-75d1-bd2e-b9842f3ed61b`;
const source = JSON.parse(await fs.readFile(`${root}/projects/criterion-memory/artifacts/user-results-aggregate-v0.1.json`, 'utf8'));
const workbook = Workbook.create();
const names = ['实验总览','复检对照','诊断数据','评分数据','轮次数据','树结构消融'];
const sheets = Object.fromEntries(names.map(name => [name, workbook.worksheets.add(name)]));
const colors = {dark:'#243B53', pale:'#F1F5F9', amber:'#FFF3CD', text:'#182B49', secondary:'#52667A'};
const coords = new Map();
const letters = n => { let s=''; while(n>0){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s; };
const percent = (a,b) => Math.round(a/b*10000)/10000;

function base(sheet, lastCol, lastRow, raw=false) {
  sheet.showGridLines = false;
  const used=sheet.getRange(`A1:${letters(lastCol)}${lastRow}`);
  used.format.font={name:'Arial',size:11,color:colors.text};
  used.format.verticalAlignment='center';
  used.format.rowHeight=27;
  used.format.columnWidthPx=115;
  if(raw){sheet.freezePanes.freezeRows(1);sheet.freezePanes.freezeColumns(2);}
}
function header(sheet, address) {
  const r=sheet.getRange(address);
  r.format={fill:colors.dark,font:{name:'Arial',size:11,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',verticalAlignment:'center',wrapText:true};
  r.format.rowHeight=44;
  r.format.borders={insideVertical:{style:'thin',color:'#FFFFFF'}};
}
function title(sheet, cell, value) { sheet.getRange(cell).values=[[value]]; sheet.getRange(cell).format.font={name:'Arial',size:16,bold:true,color:colors.dark}; }
function stripes(sheet, start, end, lastCol) { for(let row=start;row<=end;row++)if((row-start)%2===1)sheet.getRange(`A${row}:${letters(lastCol)}${row}`).format.fill=colors.pale; }
function widths(sheet, map) { for(const [col,width] of Object.entries(map))sheet.getRange(`${col}1:${col}100`).format.columnWidthPx=width; }
function numeric(sheet, address, format='0') {sheet.getRange(address).setNumberFormat(format);sheet.getRange(address).format.horizontalAlignment='right';}

// Original counts and reported rounded rates remain separate from formulas.
const diagHeaders=['记录ID','图片编号','实验ID','模型（原表）','方法','总体正确数','总体分母','正确树判对数','正确树分母','错误树排除数','错误树分母','原表总体率','原表正确树率','原表排除率','原表BA','计算总体率','计算正确树率','计算排除率','计算BA','计数/计算范围','失败政策','来源'];
const diagRows=[];
for(const figure of source.figures.filter(f=>[1,4,5,6,7].includes(f.figure))){
 const experiment=({1:'E01',4:'E02',5:'E03',6:'E04',7:'E04'})[figure.figure];
 for(const row of figure.rows){
  const r=diagRows.length+2;
  const id=`F${figure.figure}-${row.method}`;
  coords.set(id,r);
  const hasCount=typeof row.n==='number';
  diagRows.push([id,figure.figure,experiment,figure.model_label??'未注明',row.method,row.correct??null,row.n??null,row.true_tree_correct??null,row.true_tree_n??null,row.wrong_tree_rejected??null,row.wrong_tree_n??null,
   hasCount?percent(row.correct,row.n):row.accuracy_pct_reported/100,
   hasCount?percent(row.true_tree_correct,row.true_tree_n):row.true_tree_rate_pct_reported/100,
   hasCount?percent(row.wrong_tree_rejected,row.wrong_tree_n):row.wrong_tree_rejection_pct_reported/100,
   row.balanced_accuracy_pct_reported==null?null:row.balanced_accuracy_pct_reported/100,
   null,null,null,null,
   hasCount?'计数已转录；实验未审核':'计数未提供；计算BA为舍入率近似',
   figure.figure===4?'2条 Ours 失败；星号/计分未明':'未提供失败计分细则',
   `用户图片 #${figure.figure}，${row.method} 行`]);
 }
}
const ds=sheets['诊断数据'];base(ds,22,diagRows.length+1,true);
ds.getRange(`A1:V${diagRows.length+1}`).values=[diagHeaders,...diagRows];header(ds,'A1:V1');stripes(ds,2,diagRows.length+1,22);
const formulas=diagRows.map((_,i)=>{const r=i+2;return [
 `=IF(AND(ISNUMBER(F${r}),ISNUMBER(G${r}),G${r}>0),F${r}/G${r},IF(ISNUMBER(L${r}),L${r},""))`,
 `=IF(AND(ISNUMBER(H${r}),ISNUMBER(I${r}),I${r}>0),H${r}/I${r},IF(ISNUMBER(M${r}),M${r},""))`,
 `=IF(AND(ISNUMBER(J${r}),ISNUMBER(K${r}),K${r}>0),J${r}/K${r},IF(ISNUMBER(N${r}),N${r},""))`,
 `=IF(AND(ISNUMBER(Q${r}),ISNUMBER(R${r})),(Q${r}+R${r})/2,"")`
];});
ds.getRange(`P2:S${diagRows.length+1}`).formulas=formulas;
numeric(ds,`F2:K${diagRows.length+1}`);numeric(ds,`L2:S${diagRows.length+1}`,'0.00%');
ds.getRange(`P2:S${diagRows.length+1}`).format.font={name:'Arial',size:11,color:'#15646B'};
widths(ds,{A:155,B:75,C:85,D:200,E:90,F:110,G:100,H:115,I:100,J:115,K:100,L:115,M:120,N:115,O:100,P:115,Q:120,R:115,S:105,T:270,U:270,V:255});
ds.getRange(`T2:V${diagRows.length+1}`).format.wrapText=true;ds.getRange(`A2:V${diagRows.length+1}`).format.rowHeight=46;
ds.tables.add(`A1:V${diagRows.length+1}`,true,'DiagnosticRecords');

const scoreHeaders=['记录ID','图片编号','实验ID','模型（原表）','方法','临床专业性','伦理安全性','评估准确性','综合能力','问诊完整性','LLM综合评分','评分版本','来源'];
const scoreRows=[];
for(const f of source.figures.filter(f=>[1,4,5,6,7].includes(f.figure)))for(const row of f.rows){
 const s=row.scores??{};
 scoreRows.push([`F${f.figure}-${row.method}`,f.figure,({1:'E01',4:'E02',5:'E03',6:'E04',7:'E04'})[f.figure],f.model_label??'未注明',row.method,
 s.clinical_professionalism??null,s.ethical_safety??null,s.evaluation_accuracy??null,s.overall_ability??null,s.interview_completeness??null,s.llm_overall_score??row.llm_overall_score,
 f.figure===6?'与#5评分相同；#7更新评分':f.figure===7?'更新后的评分':'原表评分',`用户图片 #${f.figure}，${row.method} 行`]);
}
const ss=sheets['评分数据'];base(ss,13,scoreRows.length+1,true);
ss.getRange(`A1:M${scoreRows.length+1}`).values=[scoreHeaders,...scoreRows];header(ss,'A1:M1');stripes(ss,2,scoreRows.length+1,13);numeric(ss,`F2:K${scoreRows.length+1}`,'0.000');
widths(ss,{A:155,B:75,C:85,D:200,E:90,F:120,G:120,H:120,I:110,J:120,K:135,L:285,M:255});
ss.tables.add(`A1:M${scoreRows.length+1}`,true,'RatingRecords');

const turnFigure=source.figures.find(f=>f.figure===2);
const turnRows=turnFigure.rows.map(r=>[r.method,r.mean_turns,r.median_turns,r.true_tree_mean_turns,r.true_tree_median_turns,r.wrong_tree_mean_turns,r.wrong_tree_median_turns,r.finished_within_three_turns_count,132,null,'未注明','与主表版本未对齐','用户图片 #2，相应方法行']);
const ts=sheets['轮次数据'];base(ts,13,9,true);
ts.getRange('A1:M5').values=[['方法','总体平均轮次','总体中位轮次','正确树平均轮次','正确树中位轮次','错误树平均轮次','错误树中位轮次','≤3轮结束数','判断总数','≤3轮比例','模型','版本对应','来源'],...turnRows];header(ts,'A1:M1');stripes(ts,2,5,13);
ts.getRange('J2:J5').formulas=turnRows.map((_,i)=>[`=H${i+2}/I${i+2}`]);numeric(ts,'B2:G5','0.00');numeric(ts,'H2:I5');numeric(ts,'J2:J5','0.00%');widths(ts,{A:95,B:135,C:135,D:150,E:150,F:150,G:150,H:120,I:100,J:130,K:110,L:245,M:265});
ts.getRange('A7').values=[['平均轮次不包含所有调用成本。模型与版本未对齐，不能与 Qwen 复检表直接拼接。']];ts.getRange('A7').format.font={name:'Arial',size:11,italic:true,color:colors.secondary};
ts.tables.add('A1:M5',true,'TurnRecords');

const before=coords.get('F5-Ours'), after=coords.get('F7-Ours');
const rv=sheets['复检对照'];base(rv,7,22);title(rv,'A2','Qwen 最终独立复判前后');
rv.getRange('A4:G4').values=[['指标','复判前','复判后','净变化','单位','复判前分母','复判后分母']];header(rv,'A4:G4');
const metrics=[['总体正确数','F','项','G'],['正确树判对数','H','项','I'],['错误树排除数','J','项','K'],['总体正确率','P','比例','G'],['正确树诊断率','Q','比例','I'],['错误树排除率','R','比例','K'],['均衡准确率','S','比例',null]];
metrics.forEach(([name,col,unit,den],i)=>{const r=i+5;rv.getRange(`A${r}:G${r}`).values=[[name,null,null,null,unit==='比例'?'变化以百分点表示':unit,null,null]];
 rv.getRange(`B${r}:D${r}`).formulas=[[`='诊断数据'!${col}${before}`,`='诊断数据'!${col}${after}`,unit==='比例'?`=(C${r}-B${r})*100`:`=C${r}-B${r}`]];
 if(den)rv.getRange(`F${r}:G${r}`).formulas=[[`='诊断数据'!${den}${before}`,`='诊断数据'!${den}${after}`]];
});
numeric(rv,'B5:D7');numeric(rv,'B8:C11','0.00%');numeric(rv,'D8:D11','+0.00;-0.00;0.00');numeric(rv,'F5:G11');stripes(rv,5,11,7);
rv.getRange('A14:B18').values=[['比较范围','同模型同病例、只增加复判：研究者确认，运行日志未审'],['复判操作','对树输出做最终独立复判'],['配对改判','只知净 +7，纠错数与改坏数未提供'],['数据单位','132 项候选树判断；源病例分组待确认'],['结构改动','新增节点/DSM补树尚未匹配结果，不并入此次复判差异']];
rv.getRange('A14:A18').format.font={name:'Arial',size:11,bold:true,color:colors.secondary};widths(rv,{A:190,B:260,C:135,D:140,E:205,F:150,G:150});
rv.getRange('B14').format.wrapText=false;
rv.getRange('A20:D21').values=[['一项正确判断改变率','正确树','错误树','单位'],['比例变化',null,null,'百分点']];header(rv,'A20:D20');rv.getRange('B21:C21').formulas=[[`=100/'诊断数据'!I${before}`,`=100/'诊断数据'!K${before}`]];numeric(rv,'B21:C21','0.00');

const ov=sheets['实验总览'];base(ov,9,32);ov.tabColor=colors.dark;title(ov,'A2','诊断树实验汇总');
ov.getRange('A4').values=[['132 项候选树判断，源病例数待确认。三组主实验名称及树版本待研究者匹配。']];ov.getRange('A4').format.font={name:'Arial',size:11,italic:true,color:colors.secondary};
ov.getRange('A6:F6').values=[['Qwen 条件','总体正确率','正确树诊断率','错误树排除率','均衡准确率','总体正确数']];header(ov,'A6:F6');
['Direct','CoT','ICL','Ours 无复判','Ours 加复判'].forEach((method,i)=>{const r=i+7; const rr=coords.get(i<3?`F7-${method}`:i===3?'F5-Ours':'F7-Ours');ov.getRange(`A${r}`).values=[[method]];ov.getRange(`B${r}:F${r}`).formulas=[['P','Q','R','S','F'].map(c=>`='诊断数据'!${c}${rr}`)];});
numeric(ov,'B7:E11','0.00%');numeric(ov,'F7:F11');stripes(ov,7,11,6);
ov.getRange('A13').values=[['复检净变化见“复检对照”。图片 #6/#7 诊断数相同，评分更新，不是两次独立重复。']];ov.getRange('A13').format.font={name:'Arial',size:11,italic:true,color:colors.secondary};
ov.getRange('A16:I16').values=[['实验ID','整理类别','模型（现有记录）','涉及图片','树结构版本','复检状态','记录状态','需核对内容','研究者补充']];header(ov,'A16:I16');
const registry=[
 ['E01','主实验 A','未注明','#1','待匹配','待确认','已有诊断与评分','模型、运行版本、树改动',null],
 ['E02','主实验 B','未注明','#4','待匹配','待确认','有负结果和2条失败','模型、星号与失败计分',null],
 ['E03','主实验 Qwen','Qwen3.5-35B-A3B','#5','待匹配','未加最终复判','诊断、评分均有效','树版本、病例分组、提示',null],
 ['E04','Qwen 加复检','Qwen3.5-35B-A3B','#6/#7','据此前说明仅加复判','最终独立复判','同计数，#7评分更新','结构改动是否另有版本',null],
 ['E05','轮次附表','未注明','#2','待匹配','待确认','只有轮次表','属于哪组主实验/版本',null],
 ['E06','新增节点消融','待确认','未匹配','新增节点','待确认','未匹配结果','新节点、对照与结果表',null],
 ['E07','DSM 补树消融','待确认','未匹配','用 DSM 补充树','待确认','未匹配结果','DSM版本、改动与结果表',null],
 ['M01','方法图','不适用','#3','图示知识树','部分模块 Planned','架构，不算实验','代码实现与图示版本',null]
];
ov.getRange('A17:I24').values=registry;stripes(ov,17,24,9);ov.getRange('A17:I24').format.wrapText=true;ov.getRange('A17:I24').format.rowHeight=52;
ov.getRange('I17:I24').format.fill=colors.amber;
widths(ov,{A:190,B:155,C:225,D:135,E:225,F:200,G:220,H:250,I:270});
ov.getRange('A27').values=[['黄色列供填写实验对应关系。修改诊断数据中的计数会自动更新计算率及复检对照。']];ov.getRange('A28').values=[['原表值与计算值分列。空白代表未提供，不是 0；全部为研究者聚合材料，实验尚未独立审核。']];

const ab=sheets['树结构消融'];base(ab,11,12,true);
ab.getRange('A1:K4').values=[['消融ID','树结构','具体改动（待填写）','结果对应','模型','最终复检','正确树判对数','正确树分母','错误树排除数','错误树分母','记录状态'],
 ['S00','原始树',null,null,null,null,null,null,null,null,'基线版本待匹配'],
 ['S01','新增节点',null,null,null,null,null,null,null,null,'研究者提及，结果待匹配'],
 ['S02','DSM补充树',null,null,null,null,null,null,null,null,'研究者提及，结果待匹配']];header(ab,'A1:K1');stripes(ab,2,4,11);ab.getRange('C2:J4').format.fill=colors.amber;
widths(ab,{A:105,B:150,C:285,D:190,E:210,F:150,G:135,H:135,I:140,J:135,K:285});
ab.getRange('A6').values=[['新增节点与 DSM 补树可能重叠。先核对是否分别消融或联合修改，不假定它们已独立运行。']];
ab.getRange('A7').values=[['此前研究者确认 Qwen 110/132 到 117/132 仅增加复判，因此暂不把该差异归因于树修改。']];
ab.getRange('A8').values=[['请填写树版本、变更节点、模型、复检开关和对应图片/日志，再补入已审核的计数。']];
ab.getRange('A6:A8').format.font={name:'Arial',size:11,italic:true,color:colors.secondary};

workbook.recalculate();
// Recalculation proof: representative count edit, blank distinction, and restore.
const old=ds.getRange(`H${before}`).values[0][0];
ds.getRange(`H${before}`).values=[[30]];
workbook.recalculate();
assert(Math.abs(ds.getRange(`Q${before}`).values[0][0]-30/33)<1e-10);
assert(Math.abs(ov.getRange('C10').values[0][0]-30/33)<1e-10);
ds.getRange(`H${before}`).values=[[null]];
workbook.recalculate();
assert(Math.abs(ds.getRange(`Q${before}`).values[0][0]-percent(31,33))<1e-10);
ds.getRange(`H${before}`).values=[[old]];
workbook.recalculate();
assert(Math.abs(ov.getRange('E11').values[0][0]-(32/33+85/99)/2)<1e-10);
assert.equal(rv.getRange('D5').values[0][0],7);
assert.equal(rv.getRange('D6').values[0][0],1);
assert.equal(rv.getRange('D7').values[0][0],6);
assert.equal(ds.getRange(`F${coords.get('F4-Ours')}`).values[0][0],null);
const keyInspect = await workbook.inspect({kind:'table',range:'复检对照!A4:G11',include:'values,formulas',tableMaxRows:8,tableMaxCols:7,maxChars:4500});
console.log(keyInspect.ndjson);
const errorScan=await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'final formula error scan',maxChars:2000});
console.log(errorScan.ndjson);
const ranges={'实验总览':'A1:I28','复检对照':'A1:G22','诊断数据':'A1:V7','评分数据':'A1:M7','轮次数据':'A1:M8','树结构消融':'A1:K9'};
for(const name of names){
 const preview=await workbook.render({sheetName:name,range:ranges[name],scale:1,format:'png'});
 await fs.writeFile(`${outputDir}/preview-${names.indexOf(name)+1}.png`,new Uint8Array(await preview.arrayBuffer()));
}
const xlsx=await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(`${outputDir}/诊断树实验汇总.xlsx`);
await fs.writeFile(`${outputDir}/validation.json`,JSON.stringify({sourceFigures:7,diagnosticRows:diagRows.length,ratingRows:scoreRows.length,turnRows:turnRows.length,sheets:names,formulaErrorScan:errorScan.ndjson,countChangeRecalculation:'passed',missingVersusZero:'passed',netReviewChanges:[7,1,6],sourceGrouping:'pending',treeAblationResults:'not_matched'},null,2));
console.log(JSON.stringify({output:`${outputDir}/诊断树实验汇总.xlsx`,sheets:names,diagnosticRows:diagRows.length,ratingRows:scoreRows.length}));
