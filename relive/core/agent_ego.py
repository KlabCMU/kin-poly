import time
from relive.utils.torch_ext import *
from relive.core.agents import AgentPPO
from relive.core.common import *
from relive.core.trajbatch_ego import TrajBatchEgo


class AgentEgo(AgentPPO):

    def __init__(self, policy_vs_net=None, value_vs_net=None,  pretrain_policy_vs_net=None, pretrain_policy_net=None, **kwargs):
        super().__init__(use_mini_batch=False, **kwargs)
        self.traj_cls = TrajBatchEgo
        self.policy_vs_net = policy_vs_net
        self.value_vs_net = value_vs_net
        self.pretrain_policy_vs_net = pretrain_policy_vs_net
        self.pretrain_policy_net = pretrain_policy_net
        self.sample_modules.append(policy_vs_net)
        if self.pretrain_policy_vs_net is not None:
            self.sample_modules.append(self.pretrain_policy_vs_net)
        self.update_modules += [policy_vs_net, value_vs_net]

    def pre_sample(self):
        self.policy_vs_net.set_mode('test')
        if self.pretrain_policy_vs_net is not None:
            self.pretrain_policy_vs_net.set_mode('test')

    def pre_episode(self):
        self.policy_vs_net.initialize(tensor(self.env.get_episode_cnn_feat()))

        if self.pretrain_policy_vs_net is not None:
            self.pretrain_policy_vs_net.initialize(tensor(self.env.get_episode_cnn_feat()))

    def push_memory(self, memory, state, action, mask, next_state, reward, exp):
        v_meta = np.array([self.env.expert_ind, self.env.start_ind])
        memory.push(state, action, mask, next_state, reward, exp, v_meta)

    def trans_policy(self, states):
        return self.policy_vs_net(states)

    def trans_old_policy(self, states):
        return self.pretrain_policy_vs_net(states)

    def trans_value(self, states):
        return self.value_vs_net(states)

    def update_params(self, batch):
        t0 = time.time()
        to_train(*self.update_modules)
        states = torch.from_numpy(batch.states).to(self.dtype).to(self.device)
        actions = torch.from_numpy(batch.actions).to(self.dtype).to(self.device)
        rewards = torch.from_numpy(batch.rewards).to(self.dtype).to(self.device)
        masks = torch.from_numpy(batch.masks).to(self.dtype).to(self.device)
        exps = torch.from_numpy(batch.exps).to(self.dtype).to(self.device)
        v_metas = batch.v_metas

        self.policy_vs_net.set_mode('train')
        self.value_vs_net.set_mode('train')
        self.policy_vs_net.initialize((masks, self.env.cnn_feat, v_metas))
        self.value_vs_net.initialize((masks, self.env.cnn_feat, v_metas))
        with to_test(*self.update_modules):
            with torch.no_grad():
                values = self.value_net(self.trans_value(states))

        """get advantage estimation from the trajectories"""
        advantages, returns = estimate_advantages(rewards, masks, values, self.gamma, self.tau)

        self.update_policy(states, actions, returns, advantages, exps)

        return time.time() - t0
