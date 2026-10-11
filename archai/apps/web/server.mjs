import {mkdirSync,writeFileSync} from 'node:fs';
mkdirSync(new URL('../../logs/',import.meta.url),{recursive:true});
writeFileSync(new URL('../../logs/web-runtime.json',import.meta.url),JSON.stringify({pid:process.pid,path:process.execPath,started:new Date().toISOString()}));
// In-process development server for environments without child-process IPC.
import next from 'next';
import {createServer} from 'node:http';
const port=Number(process.env.PORT||3000);
const app=next({dev:process.env.NODE_ENV!=='production',hostname:'127.0.0.1',port});
await app.prepare();
createServer(app.getRequestHandler()).listen(port,'127.0.0.1',()=>console.log(`ArchAI ready at http://127.0.0.1:${port}`));
