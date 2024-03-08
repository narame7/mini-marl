import copy
import torch

import torch.nn.functional as F

class Train_dqn:
    def __init__(self, args):

        self.batch_size: int = args.batch_size
        self.update_iter: int = args.update_iter
        self.chunk_size: int = args.chunk_size if args.use_recurrent else 1

        self.gamma: float = args.gamma
        self.grad_clip_norm: float = args.grad_clip_norm

    def train(self, Replay_buffer, behavior_network, target_network, optimizer, epsilon):
        for _ in range(self.update_iter):
            states, actions, rewards, next_states, dones, priority_idx, importance_sampling_weight = Replay_buffer.sample(self.batch_size, self.chunk_size)
            hidden = behavior_network.init_hidden(batch_size = self.batch_size)
            target_hidden = target_network.init_hidden(batch_size = self.batch_size)
            loss = 0.0

            for step in range(self.chunk_size):
                state = states[:, step, :, :]
                action = actions[:, step, :].unsqueeze(dim=-1).long()
                reward = rewards[:, step, :]
                next_state = next_states[:, step, :, :]
                done = dones[:, step, :]

                behavior_q, next_hidden = behavior_network(state, hidden)
                max_behavior_q = behavior_q.gather(dim=2, index=action).squeeze(dim=-1)
                sum_max_behavior_q = max_behavior_q.sum(dim=1, keepdims=True)

                target_q, next_target_hidden = target_network(next_state, target_hidden.detach())
                max_target_q = target_q.max(dim=2)[0]
                sum_max_target_q = max_target_q.sum(dim=1, keepdims=True)
                target_values = importance_sampling_weight * (reward + self.gamma * (1 - done) * sum_max_target_q).sum(dim=1, keepdims=True)
                loss += F.mse_loss(target_values.detach(), sum_max_behavior_q)

                done_mask = done.squeeze(-1).bool()
                next_hidden[done_mask] = behavior_network.init_hidden(batch_size=len(next_hidden[done_mask]))
                next_target_hidden[done_mask] = behavior_network.init_hidden(batch_size=len(next_target_hidden[done_mask]))
                
                hidden = next_hidden
                target_hidden = next_target_hidden

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(parameters=behavior_network.parameters(), max_norm=self.grad_clip_norm, norm_type=2)
            optimizer.step()

            new_td_error = abs(target_values-sum_max_behavior_q)
            for index in range(self.batch_size):
                idx = priority_idx[index]
                Replay_buffer.update(idx, new_td_error[index])

class Train_double_dqn:
    def __init__(self, args):

        self.batch_size: int = args.batch_size
        self.update_iter: int = args.update_iter
        self.chunk_size: int = args.chunk_size if args.use_recurrent else 1

        self.gamma: float = args.gamma
        self.grad_clip_norm: float = args.grad_clip_norm

    def train(self, Replay_buffer, behavior_network, target_network, optimizer, epsilon):
        for _ in range(self.update_iter):
            double_network = copy.deepcopy(behavior_network)

            states, actions, rewards, next_states, dones, priority_idx, importance_sampling_weight = Replay_buffer.sample(self.batch_size, self.chunk_size)
            
            hidden = behavior_network.init_hidden(batch_size = self.batch_size)
            double_hidden = double_network.init_hidden(batch_size = self.batch_size)
            target_hidden = target_network.init_hidden(batch_size = self.batch_size)

            loss = 0.0
            for step in range(self.chunk_size):
                state = states[:, step, :, :]
                action = actions[:, step, :].unsqueeze(dim=-1).long()
                reward = rewards[:, step, :]
                next_state = next_states[:, step, :, :]
                done = dones[:, step, :]

                behavior_q, next_hidden = behavior_network(state, hidden)
                max_behavior_q = behavior_q.gather(dim=2, index=action).squeeze(dim=-1)
                sum_max_behavior_q = max_behavior_q.sum(dim=1, keepdims=True)

                target_q, next_target_hidden = target_network(next_state, target_hidden.detach())
                action, next_double_hidden, _ = double_network.sample_action(next_state, double_hidden,epsilon)
                double_q = target_q.gather(dim=2, index = action.long().unsqueeze(dim=-1)).squeeze(dim=-1)
                sum_double_q = double_q.sum(dim=1, keepdims=True)

                target_values = importance_sampling_weight * (reward + self.gamma * (1 - done) * sum_double_q).sum(dim=1, keepdims=True)
                
                loss += F.mse_loss(target_values.detach(), sum_max_behavior_q)

                done_mask = done.squeeze(-1).bool()
                next_hidden[done_mask] = behavior_network.init_hidden(batch_size=len(next_hidden[done_mask]))
                next_target_hidden[done_mask] = behavior_network.init_hidden(batch_size=len(next_target_hidden[done_mask]))
                
                hidden = next_hidden
                target_hidden = next_target_hidden
                double_hidden = next_double_hidden

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(parameters=behavior_network.parameters(), max_norm=self.grad_clip_norm, norm_type=2)
            optimizer.step()

            new_td_error = abs(target_values-sum_max_behavior_q)
            for index in range(self.batch_size):
                idx = priority_idx[index]
                Replay_buffer.update(idx, new_td_error[index])
