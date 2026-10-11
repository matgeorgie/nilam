import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
test('courtyard description generates through the wizard despite fallback defaults',async({page,request})=>{
 test.setTimeout(120000);
 const auth=await request.post('http://127.0.0.1:8000/api/auth/demo');const {token}=await auth.json();
 await page.addInitScript(value=>localStorage.setItem('archai-session',value),token);await page.goto('/projects');
 await page.getByRole('button',{name:'New project',exact:true}).click();await page.getByLabel('Project name',{exact:true}).fill('Single-floor courtyard');
 await page.getByRole('button',{name:'Continue',exact:true}).click();await page.getByRole('button',{name:'Continue',exact:true}).click();
 await page.getByLabel('Describe your home').fill(readFileSync('tests/fixtures/courtyard-brief.txt','utf8'));
 await expect(page.getByLabel('Bedrooms',{exact:true})).toBeDisabled();
 const response=page.waitForResponse(r=>r.url().endsWith('/chat')&&r.request().method()==='POST');await page.getByRole('button',{name:'Generate design',exact:true}).click();
 const result=await response;expect(result.status()).toBe(200);await page.waitForURL('**/workspace/**');const id=page.url().split('/').pop();const saved=await request.get(`http://127.0.0.1:8000/api/projects/${id}`,{headers:{Authorization:`Bearer ${token}`}});const data={project:await saved.json()};
 expect(data.project.layout.strategy).toBe('SINGLE_COURTYARD');expect(data.project.layout.rooms.filter((r:any)=>r.type==='bedroom')).toHaveLength(3);expect(data.project.layout.rooms.filter((r:any)=>r.type==='bathroom')).toHaveLength(2);expect(data.project.layout.stairs).toHaveLength(0);
 await page.waitForURL('**/workspace/**');await expect(page.getByRole('button',{name:'3D view',exact:true})).toBeVisible();
 await page.screenshot({path:'../../courtyard-plan.png',fullPage:true});
 await page.getByRole('button',{name:'3D view',exact:true}).click();await expect(page.locator('.model-container canvas')).toBeVisible({timeout:60000});
 await page.screenshot({path:'../../courtyard-3d.png',fullPage:true});
});
