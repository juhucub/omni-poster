const { spawn, spawnSync } = require('child_process');

const children = [];
const waiters = [];

function startProcess(name, command, args) {
  const child = spawn(command, args, {
    cwd: process.cwd(),
    env: { ...process.env, HOST: process.env.HOST || 'localhost', PORT: process.env.PORT || '3000' },
    stdio: 'inherit',
    shell: process.platform === 'win32',
  });

  waiters.push(
    new Promise((resolve) => {
      child.on('exit', (code, signal) => resolve({ name, code, signal }));
    })
  );

  child.on('exit', (code, signal) => {
    if (signal) {
      shutdown(signal);
      return;
    }
    if (typeof code === 'number' && code !== 0) {
      console.error(`${name} exited with code ${code}`);
      process.exitCode = code;
      shutdown('SIGTERM');
    }
  });

  children.push(child);
  return child;
}

let shuttingDown = false;

function shutdown(signal) {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) {
      child.kill(signal);
    }
  }
}

process.on('SIGINT', () => {
  shutdown('SIGINT');
  process.exit(130);
});

process.on('SIGTERM', () => {
  shutdown('SIGTERM');
  process.exit(143);
});

const cssBuild = spawnSync('npm', ['run', 'build:css'], {
  cwd: process.cwd(),
  env: { ...process.env, HOST: process.env.HOST || 'localhost', PORT: process.env.PORT || '3000' },
  stdio: 'inherit',
  shell: process.platform === 'win32',
});

if (cssBuild.status && cssBuild.status !== 0) {
  process.exit(cssBuild.status);
}

startProcess('react-scripts', 'node', ['./node_modules/react-scripts/bin/react-scripts.js', 'start']);

Promise.all(waiters).then((results) => {
  const failed = results.find((result) => typeof result.code === 'number' && result.code !== 0);
  if (failed) {
    process.exit(failed.code);
    return;
  }
  process.exit(0);
});
