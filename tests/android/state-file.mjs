// Windows can deny renaming a destination held by concurrent readers.
// Write in place; readers retry incomplete snapshots during the short write.
import fs from 'node:fs/promises';

export async function writeState(file,state){
  const content=JSON.stringify(state,null,2);
  for(let attempt=0;;++attempt){
    try{await fs.writeFile(file,content);return;}
    catch(error){
      if(!['EPERM','EACCES','EBUSY'].includes(error.code)||attempt>=49)throw error;
      await new Promise(resolve=>setTimeout(resolve,100));
    }
  }
}

export async function readState(file){
  for(let attempt=0;;++attempt){
    try{return JSON.parse(await fs.readFile(file,'utf8'));}
    catch(error){
      if((!(error instanceof SyntaxError)&&!['EPERM','EACCES','EBUSY'].includes(error.code))||attempt>=49)throw error;
      await new Promise(resolve=>setTimeout(resolve,20));
    }
  }
}
