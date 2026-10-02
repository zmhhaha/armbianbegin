export const config={
  port:Number(process.env.PORT||8080),
  databaseUrl:process.env.DATABASE_URL,
  giteaUrl:(process.env.GITEA_URL||'http://gitea.gitops.svc.cluster.local:3000').replace(/\/$/,''),
  giteaPublicUrl:(process.env.GITEA_PUBLIC_URL||'https://gitea.panghuer.top').replace(/\/$/,''),
  giteaToken:process.env.GITEA_TOKEN,
  giteaUsername:process.env.GITEA_USERNAME||'openspec-service',
  giteaOwner:process.env.GITEA_OWNER||'openspec-service',
  giteaRequestOwner:process.env.GITEA_REQUEST_OWNER||process.env.GITEA_OWNER||'openspec-service',
  giteaRequestRepository:process.env.GITEA_REQUEST_REPOSITORY||'project-requests',
  giteaWebhookSecret:process.env.GITEA_WEBHOOK_SECRET,
  giteaApprovalLabel:process.env.GITEA_APPROVAL_LABEL||'status:approved',
  giteaFailureLabel:process.env.GITEA_FAILURE_LABEL||'status:failed',
  scriptProfiles:new Set((process.env.GITEA_SCRIPT_PROFILES||'openspec-bootstrap-v1,openspec-validate-v1').split(',').map(x=>x.trim()).filter(Boolean)),
  workspaceRoot:process.env.WORKSPACE_ROOT||'/data/workspaces',
  oidcIssuer:process.env.OIDC_ISSUER,
  // 逗号分隔，可同时接受多个 audience：手工贴 JWT 与 /token 页走 panghu-suite，
  // 标准 MCP 客户端走专用应用。jose 的 jwtVerify 接受 string | string[]（见 auth.mjs）。
  oidcAudience:(process.env.OIDC_AUDIENCE||'ece3f52410b046fe0952').split(',').map(x=>x.trim()).filter(Boolean),
  oidcJwksUrl:process.env.OIDC_JWKS_URL,
  bootstrapSubjects:new Set((process.env.BOOTSTRAP_ADMIN_SUBJECTS||'').split(',').map(x=>x.trim()).filter(Boolean)),
  gitUser:process.env.GIT_USER||'openspec-service',
  gitEmail:process.env.GIT_EMAIL||'openspec-service@localhost',
  openspecBin:process.env.OPENSPEC_BIN||'/app/node_modules/.bin/openspec',
  // 项目申请表单的登录用 MCP 专用应用（公共客户端，**不需要 client_secret**）。
  // 原来给人取长期 JWT 的 GET /token 用的是 panghu-suite + CASDOOR_CLIENT_SECRET，
  // 已随「标准 MCP 客户端走 OAuth 2.1 自动授权」退役，归档在 oauth/token-dispenser/。
  casdoorMcpClientId:process.env.CASDOOR_MCP_CLIENT_ID||'315cbdaf565b82103c6f',
  publicBaseUrl:process.env.PUBLIC_BASE_URL||'https://openspec.panghuer.top'
};
