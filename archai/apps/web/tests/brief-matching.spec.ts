import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const brief=readFileSync('tests/fixtures/full-house-brief.txt','utf8');
test('exact brief works for a new project and replaces an existing design',async({page,request})=>{
 test.setTimeout(120000);
 const auth=await request.post('http://127.0.0.1:8000/api/auth/demo');const {token}=await auth.json();const headers={Authorization:`Bearer ${token}`};
 const created=await request.post('http://127.0.0.1:8000/api/projects',{headers,data:{name:'Description matching regression',specification:{plot_width:30,plot_length:50,floors:2,rooms:[{type:'bedroom',name:'Old bedroom',count:1}]}}});const project=await created.json();
 function verify(data:any){
  const rooms=data.project.layout.rooms;
  for(const [kind,floor,count] of [['bedroom',0,1],['bedroom',1,2],['bathroom',0,1],['bathroom',1,1],['balcony',1,1]])expect(rooms.filter((r:any)=>r.type===kind&&r.floor===floor)).toHaveLength(count as number);
  expect(data.project.layout.checks.filter((c:any)=>c.status==='ERROR')).toEqual([]);
 }
 const first=await request.post(`http://127.0.0.1:8000/api/projects/${project.id}/chat`,{headers,data:{message:brief}});expect(first.ok(),await first.text()).toBeTruthy();verify(await first.json());
 await page.addInitScript(value=>localStorage.setItem('archai-session',value),token);await page.goto('/workspace/'+project.id);
 await page.getByLabel('Describe a design change').fill(brief);
 const response=page.waitForResponse(r=>r.url().endsWith(`/projects/${project.id}/chat`)&&r.request().method()==='POST');await page.getByRole('button',{name:'Send message',exact:true}).click();
 const applied=await response;expect(applied.ok(),await applied.text()).toBeTruthy();verify(await applied.json());
 await expect(page.locator('.workspace-error[role=alert]')).toHaveCount(0);
 await page.screenshot({path:'../../matched-description-ground.png',fullPage:true});
 await page.getByLabel('Select floor').selectOption('1');await page.screenshot({path:'../../matched-description-upper.png',fullPage:true});
 await page.getByLabel('Describe a design change').fill('Please make everything magical');await page.getByRole('button',{name:'Send message',exact:true}).click();
 await expect(page.locator('.workspace-error[role=alert]')).toContainText('Request not applied.');
 await expect(page.locator('.workspace-error[role=alert]')).toContainText('last saved plan');
});
