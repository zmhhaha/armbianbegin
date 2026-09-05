import {config} from './config.mjs';
import * as db from './db.mjs';
import * as gitea from './gitea.mjs';
import {ServiceError} from './errors.mjs';

// Project creation is shared by the authenticated admin API and the Gitea
// issue approval path so both paths have identical rollback behavior.
export async function provisionProject({slug,username,email,createdBy,initialPermission='admin'}){
  let owner;
  let name;
  let persisted=false;
  try{
    const repository=await gitea.createPrivateRepo(slug);
    if(!repository) throw new ServiceError(409,'repo_create_failed','Gitea repository was not created');
    owner=repository.owner?.login||repository.owner?.username||config.giteaOwner;
    name=repository.name;
    await gitea.addCollaborator(owner,name,username,initialPermission);
    await gitea.initializeRepository(repository,{name:username,email:email||config.gitEmail});
    const record=(await db.insertProject({owner,repository:name,defaultBranch:repository.default_branch||'main',createdBy}));
    persisted=true;
    return{record,response:{id:record.id,owner:record.gitea_owner,repository:record.gitea_repository,revision:null}};
  }catch(error){
    if(!persisted&&owner&&name) await gitea.deleteRepo(owner,name).catch(()=>undefined);
    throw error;
  }
}
