export function referenceRuns(a,b){const x=[...(a??'')],y=[...(b??'')];if(x.length*y.length>150000)return [{text:b,differs:a!==b}];const rows=Array.from({length:x.length+1},()=>new Uint16Array(y.length+1));for(let i=x.length-1;i>=0;i--)for(let j=y.length-1;j>=0;j--)rows[i][j]=x[i]===y[j]?rows[i+1][j+1]+1:Math.max(rows[i+1][j],rows[i][j+1]);const matched=new Set();let i=0,j=0;while(i<x.length&&j<y.length){if(x[i]===y[j]){matched.add(j);i++;j++}else if(rows[i+1][j]>=rows[i][j+1])i++;else j++}const out=[];for(let k=0;k<y.length;k++){const differs=!matched.has(k);if(out.at(-1)?.differs===differs)out.at(-1).text+=y[k];else out.push({text:y[k],differs})}return out}
export const fold=s=>s.normalize('NFD').replace(/[^\p{L}]/gu,'');
export function unmatchedWords(a,b){const known=new Set(b.split(/\s+/).map(fold));return [...new Set(a.split(/\s+/).filter(s=>fold(s)&&!known.has(fold(s))))]}

// Compare both sides. Whitespace alone is ignored; marks and punctuation remain.
export function characterChanges(ocr,reference){
 const a=[...ocr.normalize('NFD')].filter(c=>!(/\s/u.test(c))),b=[...reference.normalize('NFD')].filter(c=>!(/\s/u.test(c)));
 if(a.length*b.length>1500000)return [{kind:'text (large span)',ocr:a.join(''),reference:b.join('')}];
 const cols=b.length+1,trace=new Uint8Array((a.length+1)*cols);let prev=Uint32Array.from({length:cols},(_,j)=>j);
 for(let j=1;j<cols;j++)trace[j]=2;
 for(let i=1;i<=a.length;i++){const row=new Uint32Array(cols);row[0]=i;trace[i*cols]=1;for(let j=1;j<cols;j++){const sub=prev[j-1]+(a[i-1]===b[j-1]?0:1),del=prev[j]+1,ins=row[j-1]+1;if(sub<=del&&sub<=ins){row[j]=sub;trace[i*cols+j]=0}else if(del<=ins){row[j]=del;trace[i*cols+j]=1}else{row[j]=ins;trace[i*cols+j]=2}}prev=row}
 const steps=[];let i=a.length,j=b.length;while(i||j){const t=trace[i*cols+j];if(t===0){steps.push({ocr:a[--i],reference:b[--j],op:a[i]===b[j]?'equal':'replace'})}else if(t===1)steps.push({ocr:a[--i],reference:'',op:'delete'});else steps.push({ocr:'',reference:b[--j],op:'insert'})}
 const out=[];let last=null;for(const step of steps.reverse()){if(step.op==='equal'){last=null;continue;}const chars=step.ocr+step.reference,kind=/^\p{M}+$/u.test(chars)?'Diacritics':/^\p{P}+$/u.test(chars)?'Punctuation':'Text';if(last&&last.kind===kind&&last.op===step.op&&!step.equal){last.ocr+=step.ocr;last.reference+=step.reference}else{last={kind,op:step.op,ocr:step.ocr,reference:step.reference};out.push(last)}}return out
}
