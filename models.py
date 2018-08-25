import torch
import torch.nn as nn
import torch.legacy.nn as lnn
import torch.nn.functional as F
import torch.optim as optim
import torchvision
from torch.autograd import Variable
import random, pdb, copy, os, math, numpy, copy, time
import utils



####################
# Basic modules
####################

# encodes a sequence of input frames and states, and optionally a cost or action, to a hidden representation
class encoder(nn.Module):
    def __init__(self, opt, a_size, n_inputs, states=True, state_input_size=4):
        super(encoder, self).__init__()
        self.opt = opt
        self.a_size = a_size
        self.n_inputs = opt.ncond if n_inputs is None else n_inputs
        # frame encoder
        if opt.layers == 3:
            assert(opt.nfeature % 4 == 0)
            self.feature_maps = [int(opt.nfeature/4), int(opt.nfeature/2), opt.nfeature]
            self.f_encoder = nn.Sequential(
                nn.Conv2d(3*self.n_inputs, self.feature_maps[0], 4, 2, 1),
                nn.Dropout2d(p=opt.dropout, inplace=True), 
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(self.feature_maps[0], self.feature_maps[1], 4, 2, 1),
                nn.Dropout2d(p=opt.dropout, inplace=True), 
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(self.feature_maps[1], self.feature_maps[2], 4, 2, 1),
            )
        elif opt.layers == 4:
            assert(opt.nfeature % 8 == 0)
            self.feature_maps = [int(opt.nfeature/8), int(opt.nfeature/4), int(opt.nfeature/2), opt.nfeature]
            self.f_encoder = nn.Sequential(
                nn.Conv2d(3*self.n_inputs, self.feature_maps[0], 4, 2, 1),
                nn.Dropout2d(p=opt.dropout, inplace=True), 
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(self.feature_maps[0], self.feature_maps[1], 4, 2, 1),
                nn.Dropout2d(p=opt.dropout, inplace=True), 
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(self.feature_maps[1], self.feature_maps[2], 4, 2, 1),
                nn.Dropout2d(p=opt.dropout, inplace=True), 
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(self.feature_maps[2], self.feature_maps[3], 4, 2, 1)
            )


        if states:
            n_hidden = self.feature_maps[-1]
            # state encoder
            self.s_encoder = nn.Sequential(
                nn.Linear(state_input_size*self.n_inputs, n_hidden),
                nn.Dropout(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(n_hidden, n_hidden),
                nn.Dropout(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(n_hidden, self.opt.hidden_size)
            )

        if a_size > 0:
            # action or cost encoder
            n_hidden = self.feature_maps[-1]
            self.a_encoder = nn.Sequential(
                nn.Linear(a_size, n_hidden),
                nn.Dropout(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(n_hidden, n_hidden),
                nn.Dropout(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(n_hidden, self.opt.hidden_size)
            )

    def forward(self, images, states=None, actions=None):
        bsize = images.size(0)
        h = self.f_encoder(images.view(bsize, self.n_inputs*3, self.opt.height, self.opt.width))
        if states is not None:
            h = utils.combine(h, self.s_encoder(states.contiguous().view(bsize, -1)).view(h.size()), self.opt.combine)
        if actions is not None:
            a = self.a_encoder(actions.contiguous().view(bsize, self.a_size))
            h = utils.combine(h, a.view(h.size()), self.opt.combine)
        return h




class stn(nn.Module):
    def __init__(self):
        super(stn, self).__init__()
        self.theta_net = None # TODO

    def forward(self, images, theta=None):
        images_padded = F.pad(images, (20, 20, 20, 20), "constant", 0)
        if theta is None:
            theta = self.theta_net(images)
        theta = theta.view(-1, 2, 3)
        grid = F.affine_grid(theta, images.size())
        images = F.grid_sample(images, grid)
        return images


# encodes a sequence of input frames and states, and optionally a cost or action, to a hidden representation
class encoder_stn(nn.Module):
    def __init__(self, opt, a_size, n_inputs, states=True, state_input_size=4):
        super(encoder, self).__init__()
        self.opt = opt
        self.a_size = a_size
        self.n_inputs = opt.ncond if n_inputs is None else n_inputs
        # frame encoder
        assert(opt.nfeature % 4 == 0)
        self.feature_maps = [int(opt.nfeature/4), int(opt.nfeature/2), opt.nfeature]
        self.f_encoder = nn.Sequential(
            nn.Conv2d(3*self.n_inputs, self.feature_maps[0], 4, 2, 1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(self.feature_maps[0], self.feature_maps[1], 4, 2, 1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(self.feature_maps[1], self.feature_maps[2], 4, 2, 1),
        )

        if states:
            n_hidden = self.feature_maps[-1]
            # state encoder
            self.s_encoder = nn.Sequential(
                nn.Linear(state_input_size*self.n_inputs, n_hidden),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(n_hidden, n_hidden),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(n_hidden, self.opt.hidden_size)
            )

        if a_size > 0:
            # action or cost encoder
            n_hidden = self.feature_maps[-1]
            self.a_encoder = nn.Sequential(
                nn.Linear(a_size, n_hidden),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(n_hidden, n_hidden),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(n_hidden, self.opt.hidden_size)
            )

    def forward(self, images, states=None, actions=None):
        bsize = images.size(0)
        images = images.view(bsize, self.n_inputs*3, self.opt.height, self.opt.width)
        h = self.f_encoder(images)
        if states is not None:
            h = utils.combine(h, self.s_encoder(states.contiguous().view(bsize, -1)).view(h.size()), self.opt.combine)
        if actions is not None:
            a = self.a_encoder(actions.contiguous().view(bsize, self.a_size))
            h = utils.combine(h, a.view(h.size()), self.opt.combine)
        return h




class u_network(nn.Module):
    def __init__(self, opt):
        super(u_network, self).__init__()
        self.opt = opt
        self.encoder = nn.Sequential(
            nn.Conv2d(self.opt.nfeature, self.opt.nfeature, 4, 2, 1), 
            nn.Dropout2d(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True), 
            nn.Conv2d(self.opt.nfeature, self.opt.nfeature, (4, 1), 2, 1)
        )

        self.decoder = nn.Sequential(
            nn.ConvTranspose2d(self.opt.nfeature, self.opt.nfeature, (4, 1), 2, 1),
            nn.Dropout2d(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.ConvTranspose2d(self.opt.nfeature, self.opt.nfeature, (4, 3), 2, 0)
        )

        assert(self.opt.layers == 3) # hardcoded sizes
        self.hidden_size = self.opt.nfeature*3*2
        self.fc = nn.Sequential(
            nn.Linear(self.hidden_size, self.opt.nfeature), 
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True), 
            nn.Linear(self.opt.nfeature, self.hidden_size)
        )
    
    def forward(self, h):
        h1 = self.encoder(h)
        h2 = self.fc(h1.view(-1, self.hidden_size))
        h2 = h2.view(h1.size())
        h3 = self.decoder(h2)
        return h3


# decodes a hidden state into a predicted frame, a predicted state and a predicted cost vector
class decoder(nn.Module):
    def __init__(self, opt, n_out=1):
        super(decoder, self).__init__()
        self.opt = opt
        self.n_out = n_out
        if self.opt.layers == 3:
            assert(opt.nfeature % 4 == 0)
            self.feature_maps = [int(opt.nfeature/4), int(opt.nfeature/2), opt.nfeature]
            self.f_decoder = nn.Sequential(
                nn.ConvTranspose2d(self.feature_maps[2], self.feature_maps[1], (4, 4), 2, 1),
                nn.Dropout2d(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True),
                nn.ConvTranspose2d(self.feature_maps[1], self.feature_maps[0], (5, 5), 2, (0, 1)),
                nn.Dropout2d(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True),
                nn.ConvTranspose2d(self.feature_maps[0], self.n_out*3, (2, 2), 2, (0, 1))
            )

            self.h_reducer = nn.Sequential(
                nn.Conv2d(self.feature_maps[2], self.feature_maps[2], 4, 2, 1),
                nn.Dropout2d(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Conv2d(self.feature_maps[2], self.feature_maps[2], (4, 1), (2, 1), 0),
                nn.Dropout2d(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True)
            )

        elif self.opt.layers == 4:
            assert(opt.nfeature % 8 == 0)
            self.feature_maps = [int(opt.nfeature/8), int(opt.nfeature/4), int(opt.nfeature/2), opt.nfeature]

            self.f_decoder = nn.Sequential(
                nn.ConvTranspose2d(self.feature_maps[3], self.feature_maps[2], (4, 4), 2, 1),
                nn.Dropout2d(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True),
                nn.ConvTranspose2d(self.feature_maps[2], self.feature_maps[1], (5, 5), 2, (0, 1)),
                nn.Dropout2d(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True),
                nn.ConvTranspose2d(self.feature_maps[1], self.feature_maps[0], (2, 4), 2, (1, 0)),
                nn.Dropout2d(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True),
                nn.ConvTranspose2d(self.feature_maps[0], self.n_out*3, (2, 2), 2, (1, 0))
            )

            self.h_reducer = nn.Sequential(
                nn.Conv2d(opt.nfeature, opt.nfeature, (4, 1), (2, 1), 0),
                nn.Dropout2d(p=opt.dropout, inplace=True),
                nn.LeakyReLU(0.2, inplace=True)
            )

        
        n_hidden = self.feature_maps[-1]
        self.c_predictor = nn.Sequential(
            nn.Linear(2*n_hidden, n_hidden),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(n_hidden, n_hidden),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(n_hidden, self.n_out*2),
            nn.Sigmoid()
        )

        self.s_predictor = nn.Sequential(
            nn.Linear(2*n_hidden, n_hidden),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(n_hidden, n_hidden),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(n_hidden, self.n_out*4)
        )


    def forward(self, h):
        bsize = h.size(0)
        h = h.view(bsize, self.feature_maps[-1], self.opt.h_height, self.opt.h_width)
        h_reduced = self.h_reducer(h).view(bsize, -1)
        pred_cost = self.c_predictor(h_reduced)
        pred_state = self.s_predictor(h_reduced)
        pred_image = self.f_decoder(h)
        pred_image = pred_image[:, :, :self.opt.height, :self.opt.width].clone()
        pred_image = pred_image.view(bsize, 1, 3*self.n_out, self.opt.height, self.opt.width)
        return pred_image, pred_state, pred_cost












# decodes a hidden state into a predicted frame, a predicted state and a predicted cost vector
class decoder_stn(nn.Module):
    def __init__(self, opt, n_out=1):
        super(decoder_stn, self).__init__()
        self.opt = opt
        self.n_out = n_out
        assert(opt.nfeature % 4 == 0)
        self.feature_maps = [int(opt.nfeature/4), int(opt.nfeature/2), opt.nfeature]
        self.f_decoder = nn.Sequential(
            nn.ConvTranspose2d(self.feature_maps[2], self.feature_maps[1], (4, 4), 2, 1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.ConvTranspose2d(self.feature_maps[1], self.feature_maps[1], (4, 4), 2, 1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.ConvTranspose2d(self.feature_maps[1], self.feature_maps[0], (5, 5), 2, (0, 1)),
            nn.LeakyReLU(0.2, inplace=True),
            nn.ConvTranspose2d(self.feature_maps[0], self.n_out*3, (2, 2), 2, (0, 1))
        )

        self.h_reducer = nn.Sequential(
            nn.Conv2d(self.feature_maps[2], self.feature_maps[2], 4, 2, 1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(self.feature_maps[2], self.feature_maps[2], (4, 1), (2, 1), 0),
            nn.LeakyReLU(0.2, inplace=True)
        )

        n_hidden = self.feature_maps[-1]
        self.c_predictor = nn.Sequential(
            nn.Linear(2*n_hidden, n_hidden),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(n_hidden, n_hidden),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(n_hidden, self.n_out*2),
            nn.Sigmoid()
        )

        self.s_predictor = nn.Sequential(
            nn.Linear(2*n_hidden, n_hidden),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(n_hidden, n_hidden),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(n_hidden, self.n_out*4)
        )


    def forward(self, h, actions, last_image):
        bsize = h.size(0)
        h = h.view(bsize, self.feature_maps[-1], self.opt.h_height, self.opt.h_width)
        h_reduced = self.h_reducer(h).view(bsize, -1)
        pred_cost = self.c_predictor(h_reduced)
        pred_state = self.s_predictor(h_reduced)
        pred_image_padded = self.f_decoder(h)
        pred_image = pred_image[:, :, :self.opt.height, :self.opt.width].clone()
        pred_image = pred_image.view(bsize, 1, 3*self.n_out, self.opt.height, self.opt.width)
        return pred_image, pred_state, pred_cost










# expands a latent variable to the size of the hidden representation
class z_expander(nn.Module):
    def __init__(self, opt, n_steps):
        super(z_expander, self).__init__()
        self.opt = opt
        self.n_steps = n_steps
        self.z_expander = nn.Sequential(
            nn.Linear(opt.nz, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, n_steps * opt.nfeature * self.opt.h_height * self.opt.h_width)
        )

    def forward(self, z):
        bsize = z.size(0)
        z_exp = self.z_expander(z).view(bsize, self.n_steps, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
        return z_exp



# maps a hidden representation to a distribution over latent variables. 
# We use this for the VAE models. 
class z_network_gaussian(nn.Module):
    def __init__(self, opt):
        super(z_network_gaussian, self).__init__()
        self.opt = opt

        self.network = nn.Sequential(
            nn.Linear(opt.nfeature*self.opt.h_height*self.opt.h_width, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, 2*opt.nz)
        )

    def reparameterize(self, mu, logvar, sample):
        if self.training or sample:
            std = logvar.mul(0.5).exp_()
            eps = Variable(std.data.new(std.size()).normal_())
            return eps.mul(std).add_(mu)
        else:
            return mu

    def encode(self, inputs):
        bsize = inputs.size(0)
        inputs = inputs.view(bsize, self.opt.nfeature*self.opt.h_height*self.opt.h_width)
        z_params = self.network(inputs).view(-1, self.opt.nz, 2)
        mu = z_params[:, :, 0]
        logvar = z_params[:, :, 1]
        return mu, logvar

    def forward(self, inputs, sample=True):
        mu, logvar = self.encode(inputs)
        z = self.reparameterize(mu, logvar, sample)
        return z, mu, logvar



class action_indep_net(nn.Module):
    def __init__(self, opt):
        super(action_indep_net, self).__init__()
        self.opt = opt
        self.encoder = encoder(opt, 0, opt.ncond)

        self.network_s = nn.Sequential(
            nn.Linear(opt.nfeature*self.opt.h_height*self.opt.h_width, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, 2*opt.nz)
        )

        self.network_sa = nn.Sequential(
            nn.Linear(opt.nfeature*self.opt.h_height*self.opt.h_width, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, 2*opt.nz)
        )

        self.a_encoder = nn.Sequential(
            nn.Linear(opt.n_actions, self.opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(self.opt.nfeature, self.opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(self.opt.nfeature, self.opt.hidden_size)
        )

    def forward(self, input_images, input_states, actions, z):
        bsize = input_images.size(0)
        h = self.encoder(input_images, input_states).view(bsize, self.opt.hidden_size)
        a_emb = self.a_encoder(actions).view(h.size())
        z1 = self.network_s(h).view(bsize, self.opt.nz, 2)
        z2 = self.network_sa(h + a_emb).view(bsize, self.opt.nz, 2)
        mu1 = z1[:, :, 0]
        logvar1 = z1[:, :, 1]
        mu2 = z2[:, :, 0]
        logvar2 = z2[:, :, 1]
        sigma1 = logvar1.mul(0.5).exp_()
        sigma2 = logvar1.mul(0.5).exp_()
        loss1 = utils.log_pdf(z, mu1, sigma1)
        loss2 = utils.log_pdf(z, mu2, sigma2)
        return loss1, loss2










# takes as input a sequence of frames, states and actions, and outputs the parameters of a 
# Gaussian Mixture Model. 
class PriorMDN(nn.Module):
    def __init__(self, opt):
        super(PriorMDN, self).__init__()
        self.opt = opt
        self.n_inputs = opt.ncond
        self.encoder = encoder(opt, 0, opt.ncond)

        self.network = nn.Sequential(
            nn.Linear(self.opt.hidden_size, opt.n_hidden),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.LeakyReLU(0.2, inplace=True)
        )

        self.pi_net = nn.Linear(opt.n_hidden, opt.n_mixture)
        self.mu_net = nn.Linear(opt.n_hidden, opt.n_mixture*opt.nz)
        self.sigma_net = nn.Linear(opt.n_hidden, opt.n_mixture*opt.nz)


    def forward(self, input_images, input_states):
        bsize = input_images.size(0)
        h = self.encoder(input_images, input_states).view(bsize, -1)
        h = self.network(h)
        pi = F.softmax(self.pi_net(h), dim=1)
        mu = self.mu_net(h).view(bsize, self.opt.n_mixture, self.opt.nz)
        sigma = F.softplus(self.sigma_net(h)).view(bsize, self.opt.n_mixture, self.opt.nz)
        sigma = torch.clamp(sigma, min=1e-3)
        return pi, mu, sigma


   # first extract z vectors by passing inputs, actions and targets through an external model, and uses these as targets. Useful for training the prior network to predict the z vectors inferred by a previously trained forward model. 
    def forward_thru_model(self, model, inputs, actions, targets):
        input_images, input_states = inputs
        bsize = input_images.size(0)
        npred = actions.size(1)
        ploss = Variable(torch.zeros(1).cuda())
    
        for t in range(npred):
            h_x = model.encoder(input_images, input_states)
            target_images, target_states, target_costs = targets
            h_y = model.y_encoder(target_images[:, t].unsqueeze(1).contiguous())
            z = model.z_network(utils.combine(h_x, h_y, model.opt.combine).view(bsize, -1))
            pi, mu, sigma = self(input_images, input_states)
            # prior loss
            ploss += utils.mdn_loss_fn(pi, sigma, mu, z)
            z_exp = model.z_expander(z).view(bsize, model.opt.nfeature, model.opt.h_height, model.opt.h_width)
            h_x = h_x.view(bsize, model.opt.nfeature, model.opt.h_height, model.opt.h_width)
            a_emb = model.a_encoder(actions[:, t]).view(h_x.size())
            if model.opt.zmult == 0:
                h = utils.combine(h_x, z_exp, model.opt.combine)
                h = utils.combine(h, a_emb, model.opt.combine)
            elif model.opt.zmult == 1:
                a_emb = torch.sigmoid(a_emb)
                z_exp = torch.sigmoid(z_exp)
                h = h_x + a_emb + (1-a_emb) * z_exp                
            h = h + model.u_network(h)
            pred_image, pred_state, pred_cost = model.decoder(h)

            pred_image.detach()
            pred_state.detach()
            pred_cost.detach()
            pred_image = F.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
            # since these are normalized, we are clamping to 6 standard deviations (if gaussian)
            pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)

        return ploss / npred


# takes as input a sequence of frames, states and actions, and outputs the parameters of a 
# Gaussian Mixture Model. 
class PriorGaussian(nn.Module):
    def __init__(self, opt, nz):
        super(PriorGaussian, self).__init__()
        self.opt = opt
        self.n_inputs = opt.ncond
        self.encoder = encoder(opt, 0, opt.ncond)
        self.nz = nz

        self.network = nn.Sequential(
            nn.Linear(self.opt.hidden_size, opt.n_hidden),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.LeakyReLU(0.2, inplace=True)
        )

        self.mu_net = nn.Linear(opt.n_hidden, nz)
        self.sigma_net = nn.Linear(opt.n_hidden, nz)


    def forward(self, input_images, input_states, normalize_inputs=False, normalize_outputs=False, n_samples=1):
        if normalize_inputs:
            input_images = input_images.clone().float().div_(255.0)
            input_states -= self.stats['s_mean'].view(1, 4).expand(input_states.size())
            input_states /= self.stats['s_std'].view(1, 4).expand(input_states.size())
            input_images = Variable(input_images.cuda()).unsqueeze(0)
            input_states = Variable(input_states.cuda()).unsqueeze(0)

        bsize = input_images.size(0)
        h = self.encoder(input_images, input_states).view(bsize, -1)
        h = self.network(h)
        mu = self.mu_net(h).view(bsize, self.nz)
        sigma = F.softplus(self.sigma_net(h)).view(bsize, self.nz)
        sigma = torch.clamp(sigma, min=1e-3)

        eps = Variable(torch.randn(bsize, n_samples, self.opt.n_actions).cuda())
        a = eps * sigma.view(bsize, 1, self.opt.n_actions)
        a = a + mu.view(bsize, 1, self.opt.n_actions)


        if normalize_outputs:
            a = a.data
            a *= self.stats['a_std'].view(1, 1, 2).expand(a.size()).cuda()
            a += self.stats['a_mean'].view(1, 1, 2).expand(a.size()).cuda()

        return mu, sigma, a














# Mixture Density network (fully-connected). 
class v_network_mdn_fc(nn.Module):
    def __init__(self, opt, n_outputs):
        super(v_network_mdn_fc, self).__init__()
        self.opt = opt
        self.n_outputs = n_outputs

        self.network = nn.Sequential(
            nn.Linear(self.opt.hidden_size, opt.nfeature),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nfeature),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nfeature),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True)
        )

        self.pi_net = nn.Linear(opt.nfeature, opt.n_mixture)
        self.mu_net = nn.Linear(opt.nfeature, opt.n_mixture*n_outputs)
        self.sigma_net = nn.Linear(opt.nfeature, opt.n_mixture*n_outputs)

    def forward(self, h):
        bsize = h.size(0)
        h = h.view(bsize, self.opt.hidden_size)
        h = self.network(h)
        pi = F.softmax(self.pi_net(h), dim=1)
        mu = self.mu_net(h).view(bsize, self.opt.n_mixture, self.n_outputs)
        sigma = F.softplus(self.sigma_net(h)).view(bsize, self.opt.n_mixture, self.n_outputs)
        sigma = torch.clamp(sigma, min=1e-3)
        return pi, mu, sigma



class v_network(nn.Module):
    def __init__(self, opt):
        super(v_network, self).__init__()
        self.opt = opt

        self.network = nn.Sequential(
            nn.Linear(self.opt.hidden_size, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True), 
            nn.Linear(opt.nfeature, opt.nz)
        )

    def forward(self, h):
        bsize = h.size(0)
        h = h.view(bsize, self.opt.hidden_size)
        u = self.network(h)
        u = u / torch.norm(u, 2, 1).unsqueeze(1)
        return u 







# combines a sequence of images with the state vector. 
class policy_encoder(nn.Module):
    def __init__(self, opt):
        super(policy_encoder, self).__init__()
        self.opt = opt

        self.convnet = nn.Sequential(
            nn.Conv2d(3*opt.ncond, opt.nfeature, 4, 2, 1),
            nn.ReLU(),
            nn.Conv2d(opt.nfeature, opt.nfeature, 4, 2, 1),
            nn.ReLU(),
            nn.Conv2d(opt.nfeature, opt.nfeature, 4, 2, 1),
            nn.ReLU()
        )

        self.embed = nn.Sequential(
            nn.Linear(opt.ncond*opt.n_inputs, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden)
        )

        self.hsize = opt.nfeature*self.opt.h_height*self.opt.h_width

    def forward(self, state_images, states):
        bsize = state_images.size(0)
        state_images = state_images.view(bsize, 3*self.opt.ncond, self.opt.height, self.opt.width)
        states = states.view(bsize, -1)
        hi = self.convnet(state_images).view(bsize, self.hsize)
        hs = self.embed(states)
        h = torch.cat((hi, hs), 1)
        return h


    def intype(self, t):
        if t == 'gpu':
            self.cuda()
        elif t == 'cpu':
            self.cpu()







###############
# Main models
###############

# forward model, deterministic
class FwdCNN(nn.Module):
    def __init__(self, opt, mfile):
        super(FwdCNN, self).__init__()
        self.opt = opt
        # If we are given a model file, use it to initialize this model. 
        # otherwise initialize from scratch
        if mfile == '':
            self.encoder = encoder(opt, opt.n_actions, opt.ncond)
            self.decoder = decoder(opt)
        else:
            print('[initializing encoder and decoder with: {}]'.format(mfile))
            self.mfile = mfile
            pretrained_model = torch.load(mfile)
            self.encoder = pretrained_model.encoder
            self.decoder = pretrained_model.decoder
            self.encoder.n_inputs = opt.ncond

    def forward(self, inputs, actions, target, sampling=None, z_dropout=None):
        t0 = time.time()
        npred = actions.size(1)
        input_images, input_states = inputs
        pred_images, pred_states, pred_costs = [], [], []
        for t in range(npred):
            h = self.encoder(input_images, input_states, actions[:, t])
            pred_image, pred_state, pred_cost = self.decoder(h)
            pred_image = F.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
            # since these are normalized, we are clamping to 6 standard deviations (if gaussian)
            pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        print(time.time() - t0)
        return [pred_images, pred_states, pred_costs], Variable(torch.zeros(1).cuda())

    def intype(self, t):
        if t == 'gpu':
            self.cuda()
        elif t == 'cpu':
            self.cpu()


# forward model, deterministic (compatible with TEN3 model, use to initialize)
class FwdCNN3(nn.Module):
    def __init__(self, opt, mfile):
        super(FwdCNN3, self).__init__()
        self.opt = opt
        # If we are given a model file, use it to initialize this model. 
        # otherwise initialize from scratch
        if mfile == '':
            self.encoder = encoder(opt, 0, opt.ncond)
            self.decoder = decoder(opt)
        else:
            print('[initializing encoder and decoder with: {}]'.format(mfile))
            self.mfile = mfile
            pretrained_model = torch.load(mfile)['model']
            self.encoder = pretrained_model.encoder
            self.decoder = pretrained_model.decoder
            self.a_encoder = pretrained_model.a_encoder
            self.u_network = pretrained_model.u_network
            self.encoder.n_inputs = opt.ncond


        self.a_encoder = nn.Sequential(
            nn.Linear(self.opt.n_actions, self.opt.nfeature),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(self.opt.nfeature, self.opt.nfeature),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(self.opt.nfeature, self.opt.hidden_size)
        )

        self.u_network = u_network(opt)


    def forward(self, inputs, actions, target, sampling=None, z_dropout=None):
        npred = actions.size(1)
        input_images, input_states = inputs
        pred_images, pred_states, pred_costs = [], [], []
        for t in range(npred):
            h = self.encoder(input_images, input_states)
            a_emb = self.a_encoder(actions[:, t]).view(h.size())

            if self.opt.zmult == 0:
                h = h + a_emb
            elif self.opt.zmult == 1:
                h = h + F.sigmoid(a_emb)

            h = h + self.u_network(h)
            pred_image, pred_state, pred_cost = self.decoder(h)
            pred_image = F.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
            # since these are normalized, we are clamping to 6 standard deviations (if gaussian)
            pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        return [pred_images, pred_states, pred_costs, None], Variable(torch.zeros(1).cuda())

    def intype(self, t):
        if t == 'gpu':
            self.cuda()
        elif t == 'cpu':
            self.cpu()





# this version adds the actions *after* the z variables
class FwdCNN_TEN3(nn.Module):
    def __init__(self, opt, mfile=''):
        super(FwdCNN_TEN3, self).__init__()
        self.opt = opt

        if mfile == '':
            self.encoder = encoder(opt, 0, opt.ncond)
            self.decoder = decoder(opt)
            self.a_encoder = nn.Sequential(
                nn.Linear(self.opt.n_actions, self.opt.nfeature),
                nn.Dropout(p=opt.dropout, inplace=True), 
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(self.opt.nfeature, self.opt.nfeature),
                nn.Dropout(p=opt.dropout, inplace=True), 
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(self.opt.nfeature, self.opt.hidden_size)
            )
            self.u_network = u_network(opt)

        else:
            print('[initializing encoder and decoder with: {}]'.format(mfile))
            self.mfile = mfile
            pretrained_model = torch.load(mfile)['model']
            self.encoder = pretrained_model.encoder
            self.decoder = pretrained_model.decoder
            self.a_encoder = pretrained_model.a_encoder
            self.u_network = pretrained_model.u_network
            self.encoder.n_inputs = opt.ncond
            self.decoder.n_out = 1

        self.y_encoder = encoder(opt, 0, 1, states=False)

        self.z_network = nn.Sequential(
            nn.Linear(opt.hidden_size, opt.nfeature),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nfeature),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nz)
        )

        self.z_zero = Variable(torch.zeros(self.opt.batch_size, self.opt.nz))

        if self.opt.action_indep_net == 1:
            self.action_indep_net = action_indep_net(opt)

        # if beta > 0, it means we are training a prior network jointly
        if self.opt.beta > 0:
            self.prior_network = v_network_mdn_fc(opt, self.opt.nz)

        self.z_expander = nn.Linear(opt.nz, opt.hidden_size)
        # this will store the non-parametric estimate of p(z)
        self.p_z = []

    # save a z vector in the memory buffer
    def save_z(self, z):
        if len(self.p_z) == 0:
            self.p_z = z.data.cpu()
        else:
            self.p_z = torch.cat((self.p_z, z.data.cpu()), 0)

    def compute_pz(self, dataloader, opt, nbatches):
        self.p_z = []
        for j in range(nbatches):
            print('[estimating z distribution: {:2.1%}]'.format(float(j)/nbatches), end="\r")
            inputs, actions, targets = dataloader.get_batch_fm('train', opt.npred)
            inputs = utils.make_variables(inputs)
            targets = utils.make_variables(targets)
            actions = utils.Variable(actions)
            if self.opt.zeroact == 1:
                actions.data.zero_()
            pred, loss_kl = self(inputs, actions, targets, save_z = True, sampling=None)
            del inputs, actions, targets

    # compute the nearest-neighbor graph among z vectors
    def compute_z_graph(self):
        m = self.p_z.size(0)
        # do this in CUDA...
        self.knn_indx = torch.zeros(m, 4000).cuda() # indices
        self.knn_dist = torch.zeros(m, 4000).cuda() # distances
        self.p_z = self.p_z.cuda()
        for i in range(m):
            print('[computing z graph {}]'.format(float(i)/m), end="\r")
            d = torch.norm(self.p_z - self.p_z[i].view(1, self.opt.nz), 2, 1)
            nb_dist, nb_indx = torch.topk(d, 4000, largest=False)
            self.knn_indx[i].copy_(nb_indx)
            self.knn_dist[i].copy_(nb_dist)
        self.knn_dist = self.knn_dist.cpu()
        self.knn_indx = self.knn_indx.cpu().long()
            
    # sample a latent z vector, using uniform, KNN or learned prior methods. 
    def sample_z(self, bsize, method='fp', input_images=None, input_states=None, action=None, z_prev=None, t0=False):
        z_indx = None
        if method != 'knn':
            z = []
        # fixed prior, i.e. uniform
        if method == 'fp': 
            for b in range(bsize):
                z.append(random.choice(self.p_z))
            z = torch.stack(z).contiguous()
        # at each timestep, sample on of the K nearest neighbors of the current z vector
        elif method == 'knn':
            if t0:
                # we only have the initial z vector, so quantize it first to one in the training set
                self.p_z = self.p_z.cuda()
                d = torch.norm(self.p_z.view(-1, 1, self.opt.nz) - z_prev.view(1, -1, self.opt.nz).data.cuda(), 2, 2)
                z_prev_indx = torch.topk(d, 1, dim=0, largest=False)[1].squeeze()
            else:
                z_prev, z_prev_indx = z_prev
            z, z_indx = [], []
            for b in range(bsize):
                indx = random.choice(self.knn_indx[z_prev_indx[b]][:self.opt.topz_sample])
                z_indx.append(indx)
                z.append(self.p_z[indx])
            z = torch.stack(z).contiguous()            
        # use a learned likelihood model
        elif method == 'pdf':
            M = self.p_z.size(0)
            nz = self.p_z.size(1)
            pi, mu, sigma = self.prior_network(input_images, input_states, action)
            bsize = mu.size(0)
            # sample a z vector from the likelihood model
            pi_sample = torch.multinomial(pi, 1).squeeze()
            mu_sample = torch.gather(mu, dim=1, index=pi_sample.view(bsize, 1, 1).expand(bsize, 1, nz)).squeeze()
            sigma_sample = torch.gather(sigma, dim=1, index=pi_sample.view(bsize, 1, 1).expand(bsize, 1, nz)).squeeze()
            z_sample = mu_sample.data + torch.randn(bsize, nz).cuda()*sigma_sample.data
            # quantize it to its nearest neighbor
            dist = torch.norm(self.p_z.view(-1, 1, nz) - z_sample.view(1, -1, nz), 2, 2)
            _, z_ind = torch.topk(dist, 1, dim=0, largest=False)
            z = self.p_z.index(z_ind.squeeze().cuda())
            
            
        if self.use_cuda: z = z.cuda()
        return [Variable(z), z_indx]

    # estimate prediction uncertainty using dropout
    def compute_uncertainty_batch(self, input_images, input_states, actions, targets, car_sizes, npred=200, n_models=10, Z=None, dirname=None, detach=True, compute_total_loss = False):
        bsize = input_images.size(0)
        input_images = input_images.unsqueeze(0).expand(n_models, bsize, self.opt.ncond, 3, self.opt.height, self.opt.width)
        input_states = input_states.unsqueeze(0).expand(n_models, bsize, self.opt.ncond, 4)
        input_images = input_images.contiguous().view(bsize*n_models, self.opt.ncond, 3, self.opt.height, self.opt.width)
        input_states = input_states.contiguous().view(bsize*n_models, self.opt.ncond, 4)
        actions = actions.unsqueeze(0).expand(n_models, bsize, npred, 2).contiguous().view(bsize*n_models, npred, 2)
            
        self.train() 
        if Z is None:
            Z = self.sample_z(bsize * npred, method='fp')[0]
            Z = Z.view(bsize, npred, -1)
        Z_rep = Z.unsqueeze(0).expand(n_models, bsize, npred, -1).contiguous()
        Z_rep = Z_rep.view(n_models*bsize, npred, -1)

        t0 = time.time()
        pred_images, pred_states, pred_costs = [], [], []
        for t in range(npred):
            z = Z_rep[:, t]
            pred_image, pred_state, pred_cost = self.forward_single_step(input_images, input_states, actions[:, t], z)
            if detach:
                pred_image = Variable(pred_image.data)
                pred_state = Variable(pred_state.data)
                pred_cost = Variable(pred_cost.data)

            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)

        pred_images = torch.stack(pred_images, 1).squeeze()
        pred_states = torch.stack(pred_states, 1).squeeze()
        
        pred_costs, _ = utils.proximity_cost(pred_images, Variable(pred_states.data), car_sizes.unsqueeze(0).expand(n_models, bsize, 2).contiguous().view(n_models*bsize, 2), unnormalize=True, s_mean=self.stats['s_mean'], s_std=self.stats['s_std'])

#        pred_costs = torch.stack(pred_costs, 1).squeeze()
        pred_images = pred_images.view(n_models, bsize, npred, -1)
        pred_states = pred_states.view(n_models, bsize, npred, -1)
        pred_costs = pred_costs.view(n_models, bsize, npred, -1)
        # use variance rather than standard deviation, since it is not differentiable at 0 due to sqrt
        pred_images_var = torch.var(pred_images, 0).mean(2)
        pred_states_var = torch.var(pred_states, 0).mean(2)
        pred_costs_var = torch.var(pred_costs, 0).mean(2)
        pred_costs_mean = torch.mean(pred_costs, 0)
        pred_images = pred_images.view(n_models*bsize, npred, 3, self.opt.height, self.opt.width)
        pred_states = pred_states.view(n_models*bsize, npred, 4)

        if hasattr(self, 'value_function'):
            pred_v = self.value_function(pred_images[:, -self.value_function.opt.ncond:], Variable(pred_states[:, -self.value_function.opt.ncond:].data))
            if detach:
                pred_v = Variable(pred_v.data)
            pred_v = pred_v.view(n_models, bsize)
            pred_v_var = torch.var(pred_v, 0).mean()
            pred_v_mean = torch.mean(pred_v, 0)
        else:
            pred_v_mean = Variable(torch.zeros(bsize).cuda())
            pred_v_var = Variable(torch.zeros(bsize).cuda())

        if compute_total_loss:
            u_loss_costs = F.relu((pred_costs_var - self.u_costs_mean) / self.u_costs_std - self.opt.u_hinge)
            u_loss_states = F.relu((pred_states_var - self.u_states_mean) / self.u_states_std - self.opt.u_hinge)
            u_loss_images = F.relu((pred_images_var - self.u_images_mean) / self.u_images_std - self.opt.u_hinge)
            u_loss_values = F.relu((pred_v_var - self.u_values_mean) / self.u_values_std - self.opt.u_hinge)
            total_u_loss = u_loss_costs.mean() + u_loss_states.mean() + u_loss_images.mean() 
            if hasattr(self, 'value_function'):
                total_u_loss += u_loss_values.mean()
        else:
            total_u_loss = None

        return pred_images_var, pred_states_var, pred_costs_var, pred_v_var, pred_costs_mean, pred_v_mean, total_u_loss

    # compute uncertainty estimates for the ground truth actions in the training set. 
    # this will give us an idea of what normal ranges are using actions the forward model 
    # was trained on
    def estimate_uncertainty_stats(self, dataloader, n_batches=100, npred=200):
        u_images, u_states, u_costs, u_values, speeds = [], [], [], [], []
        data_bsize = dataloader.opt.batch_size
        dataloader.opt.batch_size = 8
        for i in range(n_batches):
            print('[estimating normal uncertainty ranges: {:2.1%}]'.format(float(i)/n_batches), end="\r")
            inputs, actions, targets, ids, car_sizes = dataloader.get_batch_fm('train', npred)
            pred_images_var, pred_states_var, pred_costs_var, pred_v_var, _, _, _ = self.compute_uncertainty_batch(inputs[0], inputs[1], actions, targets, car_sizes, npred=npred, n_models=10, detach=True)
            u_images.append(pred_images_var)
            u_states.append(pred_states_var)
            u_costs.append(pred_costs_var)
            u_values.append(pred_v_var)
            speeds.append(inputs[1][:, :, 2:].norm(2, 2))

            
        
        u_images = torch.stack(u_images).view(-1, npred)
        u_states = torch.stack(u_states).view(-1, npred)
        u_costs = torch.stack(u_costs).view(-1, npred)
        u_values = torch.stack(u_values)
        speeds = torch.stack(speeds)

        self.u_images_mean = u_images.mean(0)
        self.u_states_mean = u_states.mean(0)
        self.u_costs_mean = u_costs.mean(0)
        self.u_values_mean = u_values.mean()

        self.u_images_std = u_images.std(0)
        self.u_states_std = u_states.std(0)
        self.u_costs_std = u_costs.std(0)
        self.u_values_std = u_values.std()
        dataloader.opt.batch_size = data_bsize


    def forward_single_step(self, input_images, input_states, action, z):
        # encode the inputs (without the action)
        bsize = input_images.size(0)
        h_x = self.encoder(input_images, input_states)
        z_exp = self.z_expander(z).view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
        h_x = h_x.view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
        a_emb = self.a_encoder(action).view(h_x.size())

        if self.opt.zmult == 0:
            h = utils.combine(h_x, z_exp, self.opt.combine)
            h = utils.combine(h, a_emb, self.opt.combine)
        elif self.opt.zmult == 1:
            a_emb = torch.sigmoid(a_emb)
            z_exp = torch.sigmoid(z_exp)
            h = h_x + a_emb + (1-a_emb) * z_exp

        if not self.disable_unet:
            h = h + self.u_network(h)

        pred_image, pred_state, pred_cost = self.decoder(h)
        pred_image = torch.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
        pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
        return pred_image, pred_state, pred_cost
                

    def forward(self, inputs, actions, targets, save_z = False, sampling=None, z_dropout=0.0, z_seq=None):
        input_images, input_states = inputs
        bsize = input_images.size(0)
        actions = actions.view(bsize, -1, self.opt.n_actions)
        npred = actions.size(1)
        ploss = Variable(torch.zeros(1))
        ploss2 = Variable(torch.zeros(1))
        if self.use_cuda:
            ploss = ploss.cuda()
            ploss2 = ploss2.cuda()

        pred_images, pred_states, pred_costs = [], [], []
        z_list = []

        z = None
        for t in range(npred):
            # encode the inputs (without the action)
            h_x = self.encoder(input_images, input_states)
            if sampling is None:
                # we are training or estimating z distribution
                target_images, target_states, target_costs = targets
                # encode the targets into z
                h_y = self.y_encoder(target_images[:, t].unsqueeze(1).contiguous())
                if random.random() < z_dropout:
                    if self.z_zero.size(0) == bsize:
                        z = self.z_zero
                    else:
                        self.z_zero = Variable(torch.zeros(bsize, self.opt.nz).cuda())
                        z = self.z_zero
                else:
                    z = self.z_network(utils.combine(h_x, h_y, self.opt.combine).view(bsize, -1))
                    if save_z:
                        self.save_z(z)
                    if self.opt.beta > 0:
                        pi, mu, sigma = self.prior_network(Variable(h_x.data))
                        ploss += utils.mdn_loss_fn(pi, sigma, mu, Variable(z.data))
                        if math.isnan(ploss.data[0]):
                            pdb.set_trace()                                                                
            else:
                # we are doing inference
                if z_seq is not None:
                    z = [z_seq[t], None]
                else:
                    z = self.sample_z(bsize, sampling, input_images, input_states, actions[:, t], z, t0=False)

            z_ = z if sampling is None else z[0]
            z_list.append(z_)
            z_exp = self.z_expander(z_).view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h_x = h_x.view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            a_emb = self.a_encoder(actions[:, t]).view(h_x.size())

            if self.opt.zmult == 0:
                h = utils.combine(h_x, z_exp, self.opt.combine)
                h = utils.combine(h, a_emb, self.opt.combine)
            elif self.opt.zmult == 1:
                a_emb = torch.sigmoid(a_emb)
                z_exp = torch.sigmoid(z_exp)
                h = h_x + a_emb + (1-a_emb) * z_exp
                
            if not self.disable_unet:
                h = h + self.u_network(h)

            pred_image, pred_state, pred_cost = self.decoder(h)
            if sampling is not None:
                pred_image.detach()
                pred_state.detach()
                pred_cost.detach()
            pred_image = torch.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
            # since these are normalized, we are clamping to 6 standard deviations (if gaussian)
            pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        z_list = torch.stack(z_list, 1)
        return [pred_images, pred_states, pred_costs, z_list], [ploss, ploss2]

    def reset_action_buffer(self, npred):
        self.actions_buffer = torch.zeros(npred, self.opt.n_actions).cuda()
        self.optimizer_a_stats = None

    def plan_actions_backprop(self, input_images, input_states, car_sizes, npred=50, n_futures=5, normalize=True, bprop_niter=5, bprop_lrt=1.0, u_reg=0.0, actions=None, use_action_buffer=True, n_models=10, save_opt_stats=True, nexec=1):

        if use_action_buffer:
            actions = Variable(torch.cat((self.actions_buffer[nexec:, :], torch.zeros(nexec, self.opt.n_actions).cuda()), 0).cuda())
        elif actions is None:
            actions = Variable(torch.zeros(npred, self.opt.n_actions).cuda())

        if normalize:
            input_images = input_images.clone().float().div_(255.0)
            input_states -= self.stats['s_mean'].view(1, 4).expand(input_states.size())
            input_states /= self.stats['s_std'].view(1, 4).expand(input_states.size())
            input_images = Variable(input_images.cuda()).unsqueeze(0)
            input_states = Variable(input_states.cuda()).unsqueeze(0)
        
        input_images = input_images.expand(n_futures, self.opt.ncond, 3, self.opt.height, self.opt.width)
        input_states = input_states.expand(n_futures, self.opt.ncond, 4)
        input_images = input_images.contiguous().view(n_futures, self.opt.ncond, 3, self.opt.height, self.opt.width)
        input_states = input_states.contiguous().view(n_futures, self.opt.ncond, 4)
            
        Z = self.sample_z(n_futures * npred, method='fp')[0]
        Z = Z.view(npred, n_futures, -1)
        Z0 = Z.clone()


        actions.requires_grad = True
        optimizer_a = optim.Adam([actions], bprop_lrt)
        actions_rep = actions.unsqueeze(0).expand(n_futures, npred, self.opt.n_actions)
        
        if (self.optimizer_a_stats is not None) and save_opt_stats:
            print('loading opt stats')
            optimizer_a.load_state_dict(self.optimizer_a_stats)

        gamma_mask = Variable(torch.from_numpy(numpy.array([0.99**t for t in range(npred + 1)])).float().cuda()).unsqueeze(0).expand(n_futures, npred + 1)

        #HERE
        for i in range(bprop_niter):
            optimizer_a.zero_grad()
            self.zero_grad()
            
            # first calculate proximity cost. Don't use dropout for this, it makes optimization difficult.
            self.eval()
            pred, _ = self.forward([input_images, input_states], actions_rep, None, sampling='fp', z_seq=Z)
            pred_images, pred_states = pred[0], pred[1]
            proximity_cost, _ = utils.proximity_cost(pred_images, Variable(pred_states.data), car_sizes.expand(n_futures, 2), unnormalize=True, s_mean=self.stats['s_mean'], s_std=self.stats['s_std'])

            '''
            cost = pred[2]
            proximity_cost = cost[:, :, 0]
            lane_cost = cost[:, :, 1]
            '''

            if hasattr(self, 'value_function'):
                v = self.value_function(pred[0][:, -self.value_function.opt.ncond:].contiguous(), Variable(pred[1][:, -self.value_function.opt.ncond:].contiguous().data))
            else:
                v = Variable(torch.zeros(n_futures, 1).cuda())
            proximity_loss = torch.mean(torch.cat((proximity_cost, v), 1) * gamma_mask)
            loss = proximity_loss

            

            if u_reg > 0.0:
                self.train()
                _, _, _, _, _, _, uncertainty_loss = self.compute_uncertainty_batch(input_images, input_states, actions_rep, None, car_sizes, npred=npred, n_models=n_models, Z=Z.permute(1, 0, 2).clone(), detach=False, compute_total_loss=True)
                loss = loss + u_reg * uncertainty_loss
            else:
                uncertainty_loss = Variable(torch.zeros(1))
                
#            pred_images.register_hook(lambda x: print(f'pred images, gradnorm={x.norm()}'))
            loss.backward()
            print('[iter {} | mean pred cost = {:.4f}, uncertainty = {:.4f}, grad = {}'.format(i, proximity_loss.item(), uncertainty_loss.item(), actions.grad.data.norm())) 
            torch.nn.utils.clip_grad_norm([actions], 1)
            optimizer_a.step()

        self.optimizer_a_stats = optimizer_a.state_dict()
        if use_action_buffer:
            self.actions_buffer = actions.data.clone()

        a = actions.data.view(npred, 2)

        if normalize:
            a.clamp_(-3, 3)
            a *= self.stats['a_std'].view(1, 2).expand(a.size()).cuda()
            a += self.stats['a_mean'].view(1, 2).expand(a.size()).cuda()
        return a.cpu().numpy()

    def create_policy_net(self, opt):
        if opt.policy == 'policy-gauss':
            self.policy_net = StochasticPolicy(opt)
        if opt.policy == 'policy-ten':
            self.policy_net = PolicyTEN(opt)
        elif opt.policy == 'policy-vae':
            self.policy_net = PolicyVAE(opt)

    def create_prior_net(self, opt):
        self.prior_net = PriorGaussian(opt, opt.context_dim)






    def train_policy_net_svg(self, inputs, targets, car_sizes, n_models=10, sampling_method='fp', lrt_z=0.1, n_updates_z = 10):

        input_images_orig, input_states_orig = inputs
        target_images, target_states, target_costs = targets

        input_images = input_images_orig.clone()
        input_states = input_states_orig.clone()
        bsize = input_images.size(0)
        npred = target_images.size(1)
        pred_images, pred_states, pred_costs, pred_actions = [], [], [], []
        pred_images_adv, pred_states_adv, pred_costs_adv, pred_actions_adv = None, None, None, None

        total_ploss = Variable(torch.zeros(1).cuda())
        Z = self.sample_z(npred * bsize, method=sampling_method)[0]
        Z = Z.view(npred, bsize, self.opt.nz)
        for t in range(npred):
            actions, _, _, _ = self.policy_net(input_images, input_states)
            pred_image, pred_state, pred_cost = self.forward_single_step(input_images, input_states, actions, Z[t])
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)
            pred_actions.append(actions)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        pred_actions = torch.stack(pred_actions, 1)
        
        input_images = input_images_orig.clone()
        input_states = input_states_orig.clone()
        if n_updates_z > 0:
            # optimize z vectors to be more difficult
            pred_actions = Variable(pred_actions.data.clone())
            Z.requires_grad = True
            optimizer_z = optim.Adam([Z], lrt_z)
            for k in range(n_updates_z):
                optimizer_z.zero_grad()
                pred, _ = self.forward([input_images, input_states], pred_actions, None, save_z=False, z_dropout=0.0, z_seq=Z, sampling='fixed')
                pred_cost = pred[2][:, :, 0].mean()
                _, _, _, _, _, _, total_u_loss = self.compute_uncertainty_batch(input_images, input_states, pred_actions, targets, car_sizes, npred=npred, n_models=n_models, detach=False, Z=Z.permute(1, 0, 2), compute_total_loss=True)
                loss_z = -pred_cost + total_u_loss.mean()
                loss_z.backward()
                torch.nn.utils.clip_grad_norm_([Z], 1)
                optimizer_z.step()
                print(f'[z opt | iter: {k} | pred cost: {pred_cost.item()}]')

            pred_images_adv, pred_states_adv, pred_costs_adv, pred_actions_adv = [], [], [], []
            for t in range(npred):
                actions, _, _, _ = self.policy_net(input_images, input_states)
                pred_image, pred_state, pred_cost = self.forward_single_step(input_images, input_states, actions, Z[t])
                input_images = torch.cat((input_images[:, 1:], pred_image), 1)
                input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
                pred_images_adv.append(pred_image)
                pred_states_adv.append(pred_state)
                pred_costs_adv.append(pred_cost)
                pred_actions_adv.append(actions)

            pred_images_adv = torch.cat(pred_images_adv, 1)
            pred_states_adv = torch.stack(pred_states_adv, 1)
            pred_costs_adv = torch.stack(pred_costs_adv, 1)
            pred_actions_adv = torch.stack(pred_actions_adv, 1)


        _, _, _, _, pred_costs_mean, pred_values_mean, total_u_loss = self.compute_uncertainty_batch(input_images, input_states, pred_actions, targets, car_sizes, npred=npred, n_models=n_models, detach=False, Z=Z.permute(1, 0, 2), compute_total_loss=True)

        gamma_mask = Variable(torch.from_numpy(numpy.array([0.99**t for t in range(npred+1)])).float().cuda()).unsqueeze(0)
        pred_costs_mean = pred_costs_mean[:, :, 0]
        pred_costs = torch.cat((pred_costs_mean, pred_values_mean.view(-1, 1)), 1)
        pred_costs *= gamma_mask.expand(pred_costs.size())
        pred_costs = pred_costs.mean()
        total_u_loss = total_u_loss.mean()

        return [pred_images, pred_states, pred_costs, total_u_loss], pred_actions, [pred_images_adv, pred_states_adv, pred_costs_adv]







    def train_policy_net(self, inputs, targets, targetprop=0, dropout=0.0, n_models=10):
        input_images, input_states = inputs
        target_images, target_states, target_costs = targets
        bsize = input_images.size(0)
        npred = target_images.size(1)
        pred_images, pred_states, pred_costs, pred_actions = [], [], [], []

        z = None
        total_ploss = Variable(torch.zeros(1).cuda())
        self.train()
        z_list = []
        for t in range(npred):
            actions, _, _, _ = self.policy_net(input_images, input_states)
            # encode the inputs
            h_x = self.encoder(input_images, input_states)
            # encode the targets into z
            h_y = self.y_encoder(target_images[:, t].unsqueeze(1).contiguous())
            z = self.z_network(utils.combine(h_x, h_y, self.opt.combine).view(bsize, -1))
            z_ = z
            z_list.append(z_)
            z_exp = self.z_expander(z_).view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h_x = h_x.view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            a_emb = self.a_encoder(actions).view(h_x.size())

            if self.opt.zmult == 0:
                h = utils.combine(h_x, z_exp, self.opt.combine)
                h = utils.combine(h, a_emb, self.opt.combine)
            elif self.opt.zmult == 1:
                a_emb = torch.sigmoid(a_emb)
                z_exp = torch.sigmoid(z_exp)
                h = h_x + a_emb + (1-a_emb) * z_exp
            if not self.disable_unet:
                h = h + self.u_network(h)
            pred_image, pred_state, pred_cost = self.decoder(h)
            pred_image = torch.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
            # since these are normalized, we are clamping to 6 standard deviations (if gaussian)
            pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)
            pred_actions.append(actions)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        pred_actions = torch.stack(pred_actions, 1)

        return [pred_images, pred_states, pred_costs, total_ploss], pred_actions


    def train_prior_net(self, inputs, targets):
        input_images, input_states = inputs
        target_images, target_states, target_costs = targets
        bsize = input_images.size(0)
        npred = target_images.size(1)
        pred_images, pred_states, pred_costs, pred_actions = [], [], [], []
            
        self.policy_net.cntr = 0
        actions, _, _, _, u = self.policy_net(input_images, input_states, target_images, target_states)
        mu, sigma, _ = self.prior_net(input_images, input_states)
        loss = utils.log_pdf(u, mu, sigma)
        return loss.mean()


    # assuming this is for a single input sample
    def compute_action_policy_net_v0(self, input_images, input_states, npred=50, n_futures=5, normalize=True, action_noise=0.0, bprop_niter=5, bprop_lrt=1.0):
        pred_images, pred_states, pred_costs = [], [], []

        if normalize:
            input_images = input_images.clone().float().div_(255.0)
            input_states -= self.stats['s_mean'].view(1, 4).expand(input_states.size())
            input_states /= self.stats['s_std'].view(1, 4).expand(input_states.size())
            input_images = Variable(input_images.cuda()).unsqueeze(0)
            input_states = Variable(input_states.cuda()).unsqueeze(0)

        # repeat for multiple rollouts
        bsize = n_futures 
        input_images = input_images.expand(bsize, self.opt.ncond, 3, self.opt.height, self.opt.width)
        input_states = input_states.expand(bsize, self.opt.ncond, 4)
        input_images = input_images.contiguous().view(bsize, self.opt.ncond, 3, self.opt.height, self.opt.width)
        input_states = input_states.contiguous().view(bsize, self.opt.ncond, 4)
            
        Z = self.sample_z(n_futures * npred, method='fp')[0]
        Z = Z.view(npred, n_futures, -1)
        Z0 = Z.clone()
        
        input_images_copy = input_images.clone()
        input_states_copy = input_states.clone()

        # for each future, we compute a corresponding action sequence using the policy network. 
        actions = []
        for t in range(npred):
            a, _, _, _, _ = self.policy_net(input_images, input_states, None, None)
            if t == 0 and action_noise > 0:
                a.data.add_(torch.randn(a.size()).mul_(action_noise).cuda())
            actions.append(a)
            z_ = Z[t]
            pred_image, pred_state, pred_cost = self.forward_single_step(input_images, input_states, a, z_)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        actions = torch.stack(actions, 0)
        
        # now, we evaluate each action sequence on the other futures. Reshape everything. 
        input_images_rep = input_images_copy
        input_states_rep = input_states_copy
        input_images_rep = input_images_rep.unsqueeze(0).expand(n_futures, n_futures, self.opt.ncond, 3, self.opt.height, self.opt.width).contiguous()
        input_states_rep = input_states_rep.unsqueeze(0).expand(n_futures, n_futures, self.opt.ncond, 4).contiguous()
        input_images_rep = input_images_rep.view(n_futures**2, self.opt.ncond, 3, self.opt.height, self.opt.width)
        input_states_rep = input_states_rep.view(n_futures**2, self.opt.ncond, 4)
        Z_rep = Z.unsqueeze(1).expand(npred, n_futures, n_futures, self.opt.nz).contiguous().view(npred, n_futures**2, self.opt.nz)
        actions_rep = actions.unsqueeze(2).expand(npred, n_futures, n_futures, self.opt.n_actions).contiguous().view(npred, n_futures**2, self.opt.n_actions)


        pred_images, pred_states, pred_costs = [], [], []
        for t in range(npred):
            pred_image, pred_state, pred_cost = self.forward_single_step(input_images_rep, input_states_rep, actions_rep[t], Z_rep[t])
            pred_image = Variable(pred_image.data)
            pred_state = Variable(pred_state.data)
            pred_cost = Variable(pred_cost.data)
            input_images_rep = torch.cat((input_images_rep[:, 1:], pred_image), 1)
            input_states_rep = torch.cat((input_states_rep[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_costs.append(pred_cost)
            del pred_image, pred_state, pred_cost

        pred_costs = torch.stack(pred_costs, 1)
        mean_pred_costs = pred_costs.mean(1).view(n_futures, n_futures, 2)
        # stick to the proximity cost
        mean_pred_costs = mean_pred_costs[:, :, 0]
        mean_pred_costs_over_futures = mean_pred_costs.mean(1)
        lowest_cost, indx_min = torch.min(mean_pred_costs_over_futures, 0)
        actions = Variable(actions[:, indx_min.item()].data.clone())

        # fine-tune the selected action sequence with backprop
        if lowest_cost.item() > 0.1:
            actions.requires_grad = True
            optimizer_a = optim.Adam([actions], bprop_lrt)
            actions_rep = actions.unsqueeze(0).expand(n_futures, npred, 2)
            print('[mean pred cost = {:.4f}'.format(lowest_cost.item()))
            for i in range(0, bprop_niter):
                optimizer_a.zero_grad()
                self.zero_grad()
                pred, _ = self.forward([input_images_copy, input_states_copy], actions_rep, None, sampling='fp', z_seq=Z)
                costs = pred[2]
                loss = costs[:, :, 0].mean()
                loss.backward()
                if True:
                    print('[iter {} | mean pred cost = ({:.4f}, {:.4f})], grad = {}'.format(i, costs.data[:, :, 0].mean(), costs.data[:, :, 1].mean(), actions.grad.data.norm()))
                torch.nn.utils.clip_grad_norm([actions], 1)
                actions.grad[:, 1].zero_()
                optimizer_a.step()
        a = actions[0].data
        if normalize:
            a.clamp_(-3, 3)
            a *= self.stats['a_std'].view(a.size()).cuda()
            a += self.stats['a_mean'].view(a.size()).cuda()
        return a


    # assuming this is for a single input sample
    def compute_action_policy_net(self, input_images, input_states, npred=50, n_futures=5, n_actions=10, normalize=True, action_noise=0.0):
        pred_images, pred_states, pred_costs = [], [], []

        if normalize:
            input_images = input_images.clone().float().div_(255.0)
            input_states -= self.stats['s_mean'].view(1, 4).expand(input_states.size())
            input_states /= self.stats['s_std'].view(1, 4).expand(input_states.size())
            input_images = Variable(input_images.cuda()).unsqueeze(0)
            input_states = Variable(input_states.cuda()).unsqueeze(0)


        # get initial set of actions
        a0, _, _, _, _ = self.policy_net(input_images, input_states, None, None, n_samples=n_actions, std_mult=10.0)

        # repeat for multiple rollouts
        bsize = n_futures * n_actions
        input_images = input_images.expand(bsize, self.opt.ncond, 3, self.opt.height, self.opt.width)
        input_states = input_states.expand(bsize, self.opt.ncond, 4)
        input_images = input_images.contiguous().view(bsize, self.opt.ncond, 3, self.opt.height, self.opt.width)
        input_states = input_states.contiguous().view(bsize, self.opt.ncond, 4)
            
        Z = self.sample_z(n_futures * npred, method='fp')[0]
        Z = Z.view(npred, n_futures, -1)
        Z_rep = Z.unsqueeze(1).expand(npred, n_actions, n_futures, self.opt.nz).contiguous()
        
        a = Variable(a0.data)
        a = a.unsqueeze(1).expand(n_actions, n_futures, 2).contiguous()
        a = a.view(bsize, 2)
        Z_rep = Z_rep.view(npred, bsize, self.opt.nz)

        for t in range(npred):
            z_ = Z_rep[t]
            pred_image, pred_state, pred_cost = self.forward_single_step(input_images, input_states, a, z_)
            pred_image = Variable(pred_image.data)
            pred_state = Variable(pred_state.data)
            pred_cost = Variable(pred_cost.data)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_costs.append(pred_cost)
            a, _, _, _, _ = self.policy_net(input_images, input_states, None, None)
            del pred_image, pred_state

        pred_costs = torch.stack(pred_costs, 1)
        mean_pred_costs = pred_costs.mean(1).view(n_actions, n_futures, 2)
        # stick to the proximity cost
        mean_pred_costs = mean_pred_costs[:, :, 0]
        mean_pred_costs_over_futures = mean_pred_costs.mean(1)
        print(mean_pred_costs_over_futures.data)
        _, indx_min = torch.min(mean_pred_costs_over_futures, 0)
        a = a0[indx_min.item()].data
        if normalize:
            a.clamp_(-3, 3)
            a *= self.stats['a_std'].view(a.size()).cuda()
            a += self.stats['a_mean'].view(a.size()).cuda()
        return a




        
    def intype(self, t):
        if t == 'gpu':
            self.cuda()
            self.z_zero = self.z_zero.cuda()
            self.use_cuda = True
            if len(self.p_z) > 0:
                self.p_z = self.p_z.cuda()
        elif t == 'cpu':
            self.cpu()
            self.use_cuda = False
            self.z_zero = self.z_zero.cpu()
            if len(self.p_z) > 0:
                self.p_z = self.p_z.cpu()





















# this version adds the actions *after* the z variables
class FwdCNN_VAE3(nn.Module):
    def __init__(self, opt, mfile=''):
        super(FwdCNN_VAE3, self).__init__()
        self.opt = opt

        if mfile == '':
            self.encoder = encoder(opt, 0, opt.ncond)
            self.decoder = decoder(opt)
            self.a_encoder = nn.Sequential(
                nn.Linear(self.opt.n_actions, self.opt.nfeature),
                nn.Dropout(p=opt.dropout, inplace=True), 
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(self.opt.nfeature, self.opt.nfeature),
                nn.Dropout(p=opt.dropout, inplace=True), 
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(self.opt.nfeature, self.opt.hidden_size)
            )
            self.u_network = u_network(opt)
        else:
            print('[initializing encoder and decoder with: {}]'.format(mfile))
            self.mfile = mfile
            pretrained_model = torch.load(mfile)['model']
            self.encoder = pretrained_model.encoder
            self.decoder = pretrained_model.decoder
            self.a_encoder = pretrained_model.a_encoder
            self.u_network = pretrained_model.u_network
            self.encoder.n_inputs = opt.ncond
            self.decoder.n_out = 1

        self.y_encoder = encoder(opt, 0, 1, states=False)

        self.z_network = nn.Sequential(
            nn.Linear(opt.hidden_size, opt.nfeature),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nfeature),
            nn.Dropout(p=opt.dropout, inplace=True), 
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, 2*opt.nz)
        )

        if self.opt.model == 'fwd-cnn-vae3-lp':
            self.z_network_prior = nn.Sequential(
                nn.Linear(opt.hidden_size, opt.nfeature),
                nn.Dropout(p=opt.dropout, inplace=True), 
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(opt.nfeature, opt.nfeature),
                nn.Dropout(p=opt.dropout, inplace=True), 
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(opt.nfeature, 2*opt.nz)
            )

        self.z_zero = Variable(torch.zeros(self.opt.batch_size, self.opt.nz))
        self.z_expander = nn.Linear(opt.nz, opt.hidden_size)

    def reparameterize(self, mu, logvar, sample):
        if self.training or sample:
            std = logvar.mul(0.5).exp_()
            eps = Variable(std.data.new(std.size()).normal_())
            return eps.mul(std).add_(mu)
        else:
            return mu

    def sample_z(self, h_x):
        bsize = h_x.size(0)
        if self.opt.model == 'fwd-cnn-vae3-fp':
            z = Variable(torch.randn(bsize, self.opt.nz).cuda())
        elif self.opt.model == 'fwd-cnn-vae3-lp':
            mu_logvar_prior = self.z_network_prior(h_x.view(bsize, -1)).view(bsize, 2, self.opt.nz)
            mu_prior = mu_logvar_prior[:, 0]
            logvar_prior = mu_logvar_prior[:, 1]
            z = self.reparameterize(mu_prior, logvar_prior, True)
        return z
            

    def forward(self, inputs, actions, targets, save_z = False, sampling=None, z_dropout=0.0, z_seq=None, noise=None):
        input_images, input_states = inputs
        bsize = input_images.size(0)
        actions = actions.view(bsize, -1, self.opt.n_actions)
        npred = actions.size(1)
        ploss = Variable(torch.zeros(1))
        ploss2 = Variable(torch.zeros(1))
        if self.use_cuda:
            ploss = ploss.cuda()
            ploss2 = ploss2.cuda()

        pred_images, pred_states, pred_costs = [], [], []
        z_list = []

        z = None
        for t in range(npred):
            # encode the inputs (without the action)
            h_x = self.encoder(input_images, input_states)
            if sampling is None:
                # we are training or estimating z distribution
                target_images, target_states, target_costs = targets
                # encode the targets into z
                h_y = self.y_encoder(target_images[:, t].unsqueeze(1).contiguous())
                if random.random() < z_dropout:
                    z = Variable(self.sample_z(h_x).data)
                else:
                    mu_logvar = self.z_network(utils.combine(h_x, h_y, self.opt.combine).view(bsize, -1)).view(bsize, 2, self.opt.nz)
                    mu = mu_logvar[:, 0]
                    logvar = mu_logvar[:, 1]
                    z = self.reparameterize(mu, logvar, True)
                    logvar = torch.clamp(logvar, max = 4) # this can go to inf when taking exp(), so clamp it
                    if self.opt.model == 'fwd-cnn-vae3-fp':
                        kld = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())
                        kld /= bsize
                    elif self.opt.model == 'fwd-cnn-vae3-lp':
                        mu_logvar_prior = self.z_network_prior(h_x.view(bsize, -1)).view(bsize, 2, self.opt.nz)
                        mu_prior = mu_logvar_prior[:, 0]
                        logvar_prior = mu_logvar_prior[:, 1]
                        logvar_prior = torch.clamp(logvar_prior, max = 4) # this can go to inf when taking exp(), so clamp it
                        kld = utils.kl_criterion(mu, logvar, mu_prior, logvar_prior)
                    ploss += kld
            else:
                z = self.sample_z(h_x)

            z_list.append(z)
            z_exp = self.z_expander(z).view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h_x = h_x.view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h = utils.combine(h_x, z_exp, self.opt.combine)
            a_emb = self.a_encoder(actions[:, t]).view(h.size())
            h = utils.combine(h, a_emb, self.opt.combine)
            if not self.disable_unet:
                h = h + self.u_network(h)

            pred_image, pred_state, pred_cost = self.decoder(h)
            if sampling is not None:
                pred_image.detach()
                pred_state.detach()
                pred_cost.detach()
            pred_image = torch.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
            # since these are normalized, we are clamping to 6 standard deviations (if gaussian)
            pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        z_list = torch.stack(z_list, 1)
        return [pred_images, pred_states, pred_costs, z_list], [ploss, ploss2]


    def plan_actions_backprop(self, observation, args, verbose=True, normalize=True, optimize_z=False, optimize_a=True, gamma=0.99):
        input_images, input_states = observation
        input_images = input_images.float().clone()
        input_states = input_states.clone()
        if normalize:
            input_images.div_(255.0)
            input_states -= self.stats['s_mean'].view(1, 4).expand(input_states.size())
            input_states /= self.stats['s_std'].view(1, 4).expand(input_states.size())
            input_images = Variable(input_images.cuda()).unsqueeze(0)
            input_states = Variable(input_states.cuda()).unsqueeze(0)
        bsize = input_images.size(0)
        # repeat for multiple rollouts
        input_images = input_images.unsqueeze(1).expand(bsize, args.n_rollouts, args.ncond, 3, args.height, args.width)
        input_states = input_states.unsqueeze(1).expand(bsize, args.n_rollouts, args.ncond, 4)
        input_images = input_images.contiguous().view(bsize * args.n_rollouts, args.ncond, 3, args.height, args.width)
        input_states = input_states.contiguous().view(bsize * args.n_rollouts, args.ncond, 4)
        actions = Variable(torch.randn(bsize, args.npred, self.opt.n_actions).cuda().mul_(0.0))
        if optimize_a:
            actions.requires_grad = True
            optimizer_a = optim.Adam([actions], args.lrt)

        Z = self.sample_z(bsize * args.n_rollouts * args.npred, method='fp')[0]
        Z = Z.view(args.npred, bsize * args.n_rollouts, -1)
        Z0 = Z.clone()
        gamma_mask = Variable(torch.from_numpy(numpy.array([[gamma**t, gamma**t] for t in range(args.npred)])).float().cuda()).unsqueeze(0)
        if optimize_z:
            Z.requires_grad = True
            optimizer_z = optim.Adam([Z], args.lrt)
        pred = None
        for i in range(0, args.n_iter):
            optimizer_a.zero_grad()
            self.zero_grad()
            actions_rep = actions.unsqueeze(1).expand(bsize, args.n_rollouts, args.npred, 2).contiguous().view(bsize * args.n_rollouts, args.npred, 2)
            pred, _ = self.forward([input_images, input_states], actions_rep, None, sampling='fp', z_seq=Z)
            costs = pred[2]
            weighted_costs = costs * gamma_mask
            loss = weighted_costs[:, :, 0].mean() + 0.5*weighted_costs[:, :, 1].mean()
            loss.backward()
            if verbose:
                print('[iter {} | mean pred cost = ({:.4f}, {:.4f})], grad = {}'.format(i, costs.data[:, :, 0].mean(), costs.data[:, :, 1].mean(), actions.grad.data.norm()))
            if optimize_a:
                torch.nn.utils.clip_grad_norm([actions], 1)
                optimizer_a.step()
                actions.data.clamp_(min=-2, max=2)
                actions.data[:, :, 1].clamp_(min=-1, max=1)

            if optimize_z:
                torch.nn.utils.clip_grad_norm([Z], 1)
                Z.grad *= -1
                optimizer_z.step()


        # evaluate on new futures
        Z_test = self.sample_z(bsize * args.n_rollouts * args.npred, method='fp')[0]
        Z_test = Z_test.view(args.npred, bsize * args.n_rollouts, -1)
        actions_rep = actions.unsqueeze(1).expand(bsize, args.n_rollouts, args.npred, 2).contiguous().view(bsize * args.n_rollouts, args.npred, 2)
        pred, _ = self.forward([input_images, input_states], actions_rep, None, sampling='fp', z_seq=Z_test)
        costs = pred[2]
        loss_test = costs[:, :, 0].mean() + 0.5*costs[:, :, 1].mean()
        print('\n[pred test cost = {}]\n'.format(loss_test.data[0]))
        
        '''
        # also get predictions using zero actions
        pred_const, _ = self.forward([input_images, input_states], actions.clone().zero_(), None, sampling='fp', z_seq=Z0)
        '''
        pred_const = None
        actions = actions.data.cpu()
        if normalize:
            actions *= self.stats['a_std'].view(1, 1, 2).expand(actions.size())
            actions += self.stats['a_mean'].view(1, 1, 2).expand(actions.size())
        return actions.squeeze().numpy(), pred, pred_const, loss_test.data[0]


    def create_policy_net(self, opt):
        if opt.policy == 'policy-ten':
            self.policy_net = PolicyTEN(opt)
        elif opt.policy == 'policy-vae':
            self.policy_net = PolicyVAE(opt)

    def create_prior_net(self, opt):
        self.prior_net = PriorGaussian(opt, opt.context_dim)

        

    def train_policy_net(self, inputs, targets, targetprop=0, dropout=0.0, save_z=False):
        input_images, input_states = inputs
        target_images, target_states, target_costs = targets
        bsize = input_images.size(0)
        npred = target_images.size(1)
        pred_images, pred_states, pred_costs, pred_actions = [], [], [], []
            
        z, actions_context = None, None
        total_ploss = Variable(torch.zeros(1).cuda())
        self.policy_net.cntr = 0
        for t in range(npred):
            if self.opt.actions_subsample != -1:
                next_images = target_images[:, t:t+self.opt.actions_subsample]
                next_states = target_states[:, t:t+self.opt.actions_subsample]
            else:
                next_images, next_states = None, None
            actions, ploss, _, _, u = self.policy_net(input_images, input_states, next_images, next_states, sample=False, dropout=dropout, save_z=save_z)
            total_ploss += ploss
            # encode the inputs
            h_x = self.encoder(input_images, input_states)
            # encode the targets into z
            h_y = self.y_encoder(target_images[:, t].unsqueeze(1).contiguous())
            z = self.z_network(utils.combine(h_x, h_y, self.opt.combine).view(bsize, -1))
            z_ = z
            z_exp = self.z_expander(z_).view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h_x = h_x.view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h = utils.combine(h_x, z_exp.squeeze(), self.opt.combine)
            a_emb = self.a_encoder(actions).view(h.size())
            h = utils.combine(h, a_emb, self.opt.combine)
            h = h + self.u_network(h)
            pred_image, pred_state, pred_cost = self.decoder(h)
            if self.opt.sigmoid_out == 1:
                pred_image = torch.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
            else:
                pred_image = torch.clamp(pred_image + input_images[:, -1].unsqueeze(1), min=0, max=1)
            # since these are normalized, we are clamping to 6 standard deviations (if gaussian)
            pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)
            pred_actions.append(actions)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        pred_actions = torch.stack(pred_actions, 1)
        return [pred_images, pred_states, pred_costs, ploss], pred_actions



    def train_prior_net(self, inputs, targets):
        input_images, input_states = inputs
        target_images, target_states, target_costs = targets
        bsize = input_images.size(0)
        npred = target_images.size(1)
        pred_images, pred_states, pred_costs, pred_actions = [], [], [], []
            
        self.policy_net.cntr = 0
        actions, _, _, _, u = self.policy_net(input_images, input_states, target_images, target_states)
        mu, sigma, _ = self.prior_net(input_images, input_states)
        loss = utils.log_pdf(u, mu, sigma)
        return loss.mean()




    # assuming this is for a single input sample
    def compute_action_policy_net(self, inputs, opt, npred=50, n_actions=10, n_futures=5, normalize=True):
        input_images, input_states = inputs
        pred_images, pred_states, pred_costs = [], [], []

        if normalize:
            input_images = input_images.clone().float().div_(255.0)
            input_states -= self.stats['s_mean'].view(1, 4).expand(input_states.size())
            input_states /= self.stats['s_std'].view(1, 4).expand(input_states.size())
            input_images = Variable(input_images.cuda()).unsqueeze(0)
            input_states = Variable(input_states.cuda()).unsqueeze(0)


        # repeat for multiple rollouts
        bsize = n_futures * n_actions
        input_images = input_images.expand(bsize, opt.ncond, 3, opt.height, opt.width)
        input_states = input_states.expand(bsize, opt.ncond, 4)
        input_images = input_images.contiguous().view(bsize, opt.ncond, 3, opt.height, opt.width)
        input_states = input_states.contiguous().view(bsize, opt.ncond, 4)
            
        Z = self.sample_z(n_futures * npred, method='fp')[0]
        Z = Z.view(npred, 1, n_futures, -1)
        Z = Z.expand(npred, n_actions, n_futures, -1)
        Z0 = Z.clone()

        # sample initial actions: we will choose to execute one of these at the end
        actions_init = self.policy_net(input_images[0].unsqueeze(0), input_states[0].unsqueeze(0), sample=True, normalize=False, n_samples=n_actions)
        actions = actions.clone().unsqueeze(0).expand(n_futures, n_actions, 2)
        for t in range(npred):
            # encode the inputs
            actions = self.policy_net(input_images, input_states)
            h_x = self.encoder(input_images, input_states, actions)
            z_ = Z[t]
            z_exp = self.z_expander(z_).view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h_x = h_x.view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h = utils.combine(h_x, z_exp.squeeze(), self.opt.combine)
            pred_image, pred_state, pred_cost = self.decoder(h)
            pred_image = torch.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
            # since these are normalized, we are clamping to 6 standard deviations (if gaussian)
            pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        return [pred_images, pred_states, pred_costs], None


        
    def intype(self, t):
        if t == 'gpu':
            self.cuda()
            self.z_zero = self.z_zero.cuda()
            self.use_cuda = True
        elif t == 'cpu':
            self.cpu()
            self.use_cuda = False
            self.z_zero = self.z_zero.cpu()











# this version adds the actions *after* the z variables
class FwdCNN_VAE3_STN(nn.Module):
    def __init__(self, opt, mfile=''):
        super(FwdCNN_VAE3_STN, self).__init__()
        self.opt = opt

        if mfile == '':
            self.encoder = encoder(opt, 0, opt.ncond)
            self.decoder = decoder(opt)
        else:
            print('[initializing encoder and decoder with: {}]'.format(mfile))
            self.mfile = mfile
            pretrained_model = torch.load(mfile)['model']
            self.encoder = pretrained_model.encoder
            self.decoder = pretrained_model.decoder
            self.a_encoder = pretrained_model.a_encoder
            self.u_network = pretrained_model.u_network
            self.encoder.n_inputs = opt.ncond
            self.decoder.n_out = 1

        self.y_encoder = encoder(opt, 0, 1, states=False)

        self.a_encoder = nn.Sequential(
            nn.Linear(self.opt.n_actions, self.opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(self.opt.nfeature, self.opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(self.opt.nfeature, self.opt.hidden_size)
        )

        self.u_network = u_network(opt)

        self.z_network = nn.Sequential(
            nn.Linear(opt.hidden_size, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, opt.nfeature),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(opt.nfeature, 2*opt.nz)
        )

        if self.opt.model == 'fwd-cnn-vae3-lp':
            self.z_network_prior = nn.Sequential(
                nn.Linear(opt.hidden_size, opt.nfeature),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(opt.nfeature, opt.nfeature),
                nn.LeakyReLU(0.2, inplace=True),
                nn.Linear(opt.nfeature, 2*opt.nz)
            )


        self.z_zero = Variable(torch.zeros(self.opt.batch_size, self.opt.nz))
        self.z_expander = nn.Linear(opt.nz, opt.hidden_size)

    def reparameterize(self, mu, logvar, sample):
        if self.training or sample:
            std = logvar.mul(0.5).exp_()
            eps = Variable(std.data.new(std.size()).normal_())
            return eps.mul(std).add_(mu)
        else:
            return mu

    def sample_z(self, h_x):
        bsize = h_x.size(0)
        if self.opt.model == 'fwd-cnn-vae3-fp':
            z = Variable(torch.randn(bsize, self.opt.nz).cuda())
        elif self.opt.model == 'fwd-cnn-vae3-lp':
            mu_logvar_prior = self.z_network_prior(h_x.view(bsize, -1)).view(bsize, 2, self.opt.nz)
            mu_prior = mu_logvar_prior[:, 0]
            logvar_prior = mu_logvar_prior[:, 1]
            z = self.reparameterize(mu_prior, logvar_prior, True)
        return z
            

    def forward(self, inputs, actions, targets, save_z = False, sampling=None, z_dropout=0.0, z_seq=None, noise=None):
        input_images, input_states = inputs
        bsize = input_images.size(0)
        actions = actions.view(bsize, -1, self.opt.n_actions)
        npred = actions.size(1)
        ploss = Variable(torch.zeros(1))
        ploss2 = Variable(torch.zeros(1))
        if self.use_cuda:
            ploss = ploss.cuda()
            ploss2 = ploss2.cuda()

        pred_images, pred_states, pred_costs = [], [], []
        z_list = []

        z = None
        for t in range(npred):
            # encode the inputs (without the action)
            h_x = self.encoder(input_images, input_states)
            if sampling is None:
                # we are training or estimating z distribution
                target_images, target_states, target_costs = targets
                # encode the targets into z
                h_y = self.y_encoder(target_images[:, t].unsqueeze(1).contiguous())
                if random.random() < z_dropout:
                    z = Variable(self.sample_z(h_x).data)
                else:
                    mu_logvar = self.z_network(utils.combine(h_x, h_y, self.opt.combine).view(bsize, -1)).view(bsize, 2, self.opt.nz)
                    mu = mu_logvar[:, 0]
                    logvar = mu_logvar[:, 1]
                    z = self.reparameterize(mu, logvar, True)
                    logvar = torch.clamp(logvar, max = 4) # this can go to inf when taking exp(), so clamp it
                    if self.opt.model == 'fwd-cnn-vae3-fp':
                        kld = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())
                        kld /= bsize
                    elif self.opt.model == 'fwd-cnn-vae3-lp':
                        mu_logvar_prior = self.z_network_prior(h_x.view(bsize, -1)).view(bsize, 2, self.opt.nz)
                        mu_prior = mu_logvar_prior[:, 0]
                        logvar_prior = mu_logvar_prior[:, 1]
                        kld = utils.kl_criterion(mu, logvar, mu_prior, logvar_prior)
                    ploss += kld
            else:
                z = self.sample_z(h_x)

            z_list.append(z)
            z_exp = self.z_expander(z).view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h_x = h_x.view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h = utils.combine(h_x, z_exp, self.opt.combine)
            a_emb = self.a_encoder(actions[:, t]).view(h.size())
            h = utils.combine(h, a_emb, self.opt.combine)
            h = h + self.u_network(h)

            pred_image, pred_state, pred_cost = self.decoder(h)



            if sampling is not None:
                pred_image.detach()
                pred_state.detach()
                pred_cost.detach()
            if self.opt.sigmoid_out == 1:
                pred_image = torch.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
            else:
                pred_image = torch.clamp(pred_image + input_images[:, -1].unsqueeze(1), min=0, max=1)
            # since these are normalized, we are clamping to 6 standard deviations (if gaussian)
            pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        z_list = torch.stack(z_list, 1)
        return [pred_images, pred_states, pred_costs, z_list], [ploss, ploss2]


    def plan_actions_backprop(self, observation, args, verbose=True, normalize=True, optimize_z=False, optimize_a=True, gamma=0.99):
        input_images, input_states = observation
        input_images = input_images.float().clone()
        input_states = input_states.clone()
        if normalize:
            input_images.div_(255.0)
            input_states -= self.stats['s_mean'].view(1, 4).expand(input_states.size())
            input_states /= self.stats['s_std'].view(1, 4).expand(input_states.size())
            input_images = Variable(input_images.cuda()).unsqueeze(0)
            input_states = Variable(input_states.cuda()).unsqueeze(0)
        bsize = input_images.size(0)
        # repeat for multiple rollouts
        input_images = input_images.unsqueeze(1).expand(bsize, args.n_rollouts, args.ncond, 3, args.height, args.width)
        input_states = input_states.unsqueeze(1).expand(bsize, args.n_rollouts, args.ncond, 4)
        input_images = input_images.contiguous().view(bsize * args.n_rollouts, args.ncond, 3, args.height, args.width)
        input_states = input_states.contiguous().view(bsize * args.n_rollouts, args.ncond, 4)
        actions = Variable(torch.randn(bsize, args.npred, self.opt.n_actions).cuda().mul_(0.0))
        if optimize_a:
            actions.requires_grad = True
            optimizer_a = optim.Adam([actions], args.lrt)

        Z = self.sample_z(bsize * args.n_rollouts * args.npred, method='fp')[0]
        Z = Z.view(args.npred, bsize * args.n_rollouts, -1)
        Z0 = Z.clone()
        gamma_mask = Variable(torch.from_numpy(numpy.array([[gamma**t, gamma**t] for t in range(args.npred)])).float().cuda()).unsqueeze(0)
        if optimize_z:
            Z.requires_grad = True
            optimizer_z = optim.Adam([Z], args.lrt)
        pred = None
        for i in range(0, args.n_iter):
            optimizer_a.zero_grad()
            self.zero_grad()
            actions_rep = actions.unsqueeze(1).expand(bsize, args.n_rollouts, args.npred, 2).contiguous().view(bsize * args.n_rollouts, args.npred, 2)
            pred, _ = self.forward([input_images, input_states], actions_rep, None, sampling='fp', z_seq=Z)
            costs = pred[2]
            weighted_costs = costs * gamma_mask
            loss = weighted_costs[:, :, 0].mean() + 0.5*weighted_costs[:, :, 1].mean()
            loss.backward()
            if verbose:
                print('[iter {} | mean pred cost = ({:.4f}, {:.4f})], grad = {}'.format(i, costs.data[:, :, 0].mean(), costs.data[:, :, 1].mean(), actions.grad.data.norm()))
            if optimize_a:
                torch.nn.utils.clip_grad_norm([actions], 1)
                optimizer_a.step()
                actions.data.clamp_(min=-2, max=2)
                actions.data[:, :, 1].clamp_(min=-1, max=1)

            if optimize_z:
                torch.nn.utils.clip_grad_norm([Z], 1)
                Z.grad *= -1
                optimizer_z.step()


        # evaluate on new futures
        Z_test = self.sample_z(bsize * args.n_rollouts * args.npred, method='fp')[0]
        Z_test = Z_test.view(args.npred, bsize * args.n_rollouts, -1)
        actions_rep = actions.unsqueeze(1).expand(bsize, args.n_rollouts, args.npred, 2).contiguous().view(bsize * args.n_rollouts, args.npred, 2)
        pred, _ = self.forward([input_images, input_states], actions_rep, None, sampling='fp', z_seq=Z_test)
        costs = pred[2]
        loss_test = costs[:, :, 0].mean() + 0.5*costs[:, :, 1].mean()
        print('\n[pred test cost = {}]\n'.format(loss_test.data[0]))
        
        '''
        # also get predictions using zero actions
        pred_const, _ = self.forward([input_images, input_states], actions.clone().zero_(), None, sampling='fp', z_seq=Z0)
        '''
        pred_const = None
        actions = actions.data.cpu()
        if normalize:
            actions *= self.stats['a_std'].view(1, 1, 2).expand(actions.size())
            actions += self.stats['a_mean'].view(1, 1, 2).expand(actions.size())
        return actions.squeeze().numpy(), pred, pred_const, loss_test.data[0]


    def create_policy_net(self, opt):
        if opt.policy == 'policy-gauss':
            self.policy_net = StochasticPolicy(opt)
        elif opt.policy == 'policy-ten':
            self.policy_net = PolicyTEN(opt)
        elif opt.policy == 'policy-vae':
            self.policy_net = PolicyVAE(opt)

    def create_prior_net(self, opt):
        self.prior_net = PriorGaussian(opt, opt.context_dim)

        

    def train_policy_net(self, inputs, targets, targetprop=0, dropout=0.0, save_z=False):
        input_images, input_states = inputs
        target_images, target_states, target_costs = targets
        bsize = input_images.size(0)
        npred = target_images.size(1)
        pred_images, pred_states, pred_costs, pred_actions = [], [], [], []
            
        z, actions_context = None, None
        total_ploss = Variable(torch.zeros(1).cuda())
        self.policy_net.cntr = 0
        for t in range(npred):
            if self.opt.actions_subsample != -1:
                next_images = target_images[:, t:t+self.opt.actions_subsample]
                next_states = target_states[:, t:t+self.opt.actions_subsample]
            else:
                next_images, next_states = None, None
            actions, ploss, _, _, u = self.policy_net(input_images, input_states, next_images, next_states, sample=False, dropout=dropout, save_z=save_z)
            total_ploss += ploss
            # encode the inputs
            h_x = self.encoder(input_images, input_states)
            # encode the targets into z
            h_y = self.y_encoder(target_images[:, t].unsqueeze(1).contiguous())
            z = self.z_network(utils.combine(h_x, h_y, self.opt.combine).view(bsize, -1))
            z_ = z
            z_exp = self.z_expander(z_).view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h_x = h_x.view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h = utils.combine(h_x, z_exp.squeeze(), self.opt.combine)
            a_emb = self.a_encoder(actions).view(h.size())
            h = utils.combine(h, a_emb, self.opt.combine)
            h = h + self.u_network(h)
            pred_image, pred_state, pred_cost = self.decoder(h)
            if self.opt.sigmoid_out == 1:
                pred_image = torch.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
            else:
                pred_image = torch.clamp(pred_image + input_images[:, -1].unsqueeze(1), min=0, max=1)
            # since these are normalized, we are clamping to 6 standard deviations (if gaussian)
            pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)
            pred_actions.append(actions)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        pred_actions = torch.stack(pred_actions, 1)
        return [pred_images, pred_states, pred_costs, ploss], pred_actions



    def train_prior_net(self, inputs, targets):
        input_images, input_states = inputs
        target_images, target_states, target_costs = targets
        bsize = input_images.size(0)
        npred = target_images.size(1)
        pred_images, pred_states, pred_costs, pred_actions = [], [], [], []
            
        self.policy_net.cntr = 0
        actions, _, _, _, u = self.policy_net(input_images, input_states, target_images, target_states)
        mu, sigma, _ = self.prior_net(input_images, input_states)
        loss = utils.log_pdf(u, mu, sigma)
        return loss.mean()




    # assuming this is for a single input sample
    def compute_action_policy_net(self, inputs, opt, npred=50, n_actions=10, n_futures=5, normalize=True):
        input_images, input_states = inputs
        pred_images, pred_states, pred_costs = [], [], []

        if normalize:
            input_images = input_images.clone().float().div_(255.0)
            input_states -= self.stats['s_mean'].view(1, 4).expand(input_states.size())
            input_states /= self.stats['s_std'].view(1, 4).expand(input_states.size())
            input_images = Variable(input_images.cuda()).unsqueeze(0)
            input_states = Variable(input_states.cuda()).unsqueeze(0)


        # repeat for multiple rollouts
        bsize = n_futures * n_actions
        input_images = input_images.expand(bsize, opt.ncond, 3, opt.height, opt.width)
        input_states = input_states.expand(bsize, opt.ncond, 4)
        input_images = input_images.contiguous().view(bsize, opt.ncond, 3, opt.height, opt.width)
        input_states = input_states.contiguous().view(bsize, opt.ncond, 4)
            
        Z = self.sample_z(n_futures * npred, method='fp')[0]
        Z = Z.view(npred, 1, n_futures, -1)
        Z = Z.expand(npred, n_actions, n_futures, -1)
        Z0 = Z.clone()

        # sample initial actions: we will choose to execute one of these at the end
        actions_init = self.policy_net(input_images[0].unsqueeze(0), input_states[0].unsqueeze(0), sample=True, normalize=False, n_samples=n_actions)
        actions = actions.clone().unsqueeze(0).expand(n_futures, n_actions, 2)
        for t in range(npred):
            # encode the inputs
            actions = self.policy_net(input_images, input_states)
            h_x = self.encoder(input_images, input_states, actions)
            z_ = Z[t]
            z_exp = self.z_expander(z_).view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h_x = h_x.view(bsize, self.opt.nfeature, self.opt.h_height, self.opt.h_width)
            h = utils.combine(h_x, z_exp.squeeze(), self.opt.combine)
            pred_image, pred_state, pred_cost = self.decoder(h)
            pred_image = torch.sigmoid(pred_image + input_images[:, -1].unsqueeze(1))
            # since these are normalized, we are clamping to 6 standard deviations (if gaussian)
            pred_state = torch.clamp(pred_state + input_states[:, -1], min=-6, max=6)
            input_images = torch.cat((input_images[:, 1:], pred_image), 1)
            input_states = torch.cat((input_states[:, 1:], pred_state.unsqueeze(1)), 1)
            pred_images.append(pred_image)
            pred_states.append(pred_state)
            pred_costs.append(pred_cost)

        pred_images = torch.cat(pred_images, 1)
        pred_states = torch.stack(pred_states, 1)
        pred_costs = torch.stack(pred_costs, 1)
        return [pred_images, pred_states, pred_costs], None


        
    def intype(self, t):
        if t == 'gpu':
            self.cuda()
            self.z_zero = self.z_zero.cuda()
            self.use_cuda = True
        elif t == 'cpu':
            self.cpu()
            self.use_cuda = False
            self.z_zero = self.z_zero.cpu()












class LSTMCritic(nn.Module):
    def __init__(self, opt, batch_size=None):
        super(LSTMCritic, self).__init__()
        self.opt = copy.deepcopy(opt)
        self.opt.ncond = 1
        if batch_size is None:
            batch_size = opt.batch_size
        self.encoder = encoder(self.opt, 0, 1, state_input_size=6)
        self.input_size = opt.nfeature*opt.h_height*opt.h_width
        self.lstm = nn.LSTM(self.input_size, opt.nhidden)
        self.classifier = nn.Linear(opt.nhidden, 1)
        self.hidden = (Variable(torch.randn(1, batch_size, opt.nhidden).cuda()),
                       Variable(torch.randn(1, batch_size, opt.nhidden).cuda()))


    def forward(self, inputs):
        input_images, input_states = inputs
        input_images.detach()
        input_states.detach()        
        bsize = input_images.size(0)
        self.hidden = (Variable(torch.randn(1, bsize, self.opt.nhidden).cuda()),Variable(torch.randn(1, bsize, self.opt.nhidden).cuda()))
        T = input_images.size(1)
        for t in range(T):
            enc = self.encoder(input_images[:, t].contiguous(), input_states[:, t].contiguous())
            out, self.hidden = self.lstm(enc.view(1, bsize, -1), self.hidden)
        logits = self.classifier(out.squeeze())
        return logits.squeeze()



#######################################
# Policy Networks
#######################################

# deterministic CNN model
class PolicyCNN(nn.Module):
    def __init__(self, opt):
        super(PolicyCNN, self).__init__()
        self.opt = opt
        self.encoder = encoder(opt)
        self.hsize = opt.nfeature*self.opt.h_height*self.opt.h_width
        self.fc = nn.Sequential(
            nn.Linear(self.hsize + opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.npred*opt.n_actions)
        )

    def forward(self, state_images, states, actions):
        bsize = state_images.size(0)
        h = self.encoder(state_images, states)
        a = self.fc(h)
        a = a.view(bsize, self.opt.npred, self.opt.n_actions)
        return a, Variable(torch.zeros(1))


    def intype(self, t):
        if t == 'gpu':
            self.cuda()
        elif t == 'cpu':
            self.cpu()



# Stochastic Policy, output is a diagonal Gaussian and learning
# uses the reparameterization trick. 
class StochasticPolicy(nn.Module):
    def __init__(self, opt, context_dim=0, output_dim=None):
        super(StochasticPolicy, self).__init__()
        self.opt = opt
        self.encoder = encoder(opt, 0, opt.ncond)
        self.hsize = opt.nfeature*self.opt.h_height*self.opt.h_width
        self.n_outputs = opt.n_actions if output_dim is None else output_dim
        self.proj = nn.Linear(self.hsize, opt.n_hidden)
        self.context_dim = context_dim

        self.fc = nn.Sequential(
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden)
        )

        if context_dim > 0:
            self.context_encoder = nn.Sequential(
                nn.Linear(context_dim, opt.n_hidden), 
                nn.ReLU(), 
                nn.Linear(opt.n_hidden, opt.n_hidden), 
                nn.ReLU(), 
                nn.Linear(opt.n_hidden, opt.n_hidden)
            )

        self.mu_net = nn.Linear(opt.n_hidden, self.n_outputs)
        self.logvar_net = nn.Linear(opt.n_hidden, self.n_outputs)


    def forward(self, state_images, states, context=None, sample=True, normalize_inputs=False, normalize_outputs=False, n_samples=1, std_mult=1.0):

        if normalize_inputs:
            state_images = state_images.clone().float().div_(255.0)
            states -= self.stats['s_mean'].view(1, 4).expand(states.size())
            states /= self.stats['s_std'].view(1, 4).expand(states.size())
            state_images = Variable(state_images.cuda()).unsqueeze(0)
            states = Variable(states.cuda()).unsqueeze(0)


        bsize = state_images.size(0)

        h = self.encoder(state_images, states).view(bsize, self.hsize)
        h = self.proj(h)
        if self.context_dim > 0:
            assert(context is not None)
            h = h + self.context_encoder(context)
        h = self.fc(h)
        mu = self.mu_net(h).view(bsize, self.n_outputs)
        logvar = self.logvar_net(h).view(bsize, self.n_outputs)
        logvar = torch.clamp(logvar, max = 4.0)
        std = logvar.mul(0.5).exp_()
        eps = Variable(torch.randn(bsize, n_samples, self.n_outputs).cuda())
        a = eps * std.view(bsize, 1, self.n_outputs) * std_mult
        a = a + mu.view(bsize, 1, self.n_outputs)

        if normalize_outputs:
            a = a.data
            a.clamp_(-3, 3)
            a *= self.stats['a_std'].view(1, 1, 2).expand(a.size()).cuda()
            a += self.stats['a_mean'].view(1, 1, 2).expand(a.size()).cuda()

        entropy = std.mean()
        return a.squeeze(), entropy, mu, std


    def intype(self, t):
        if t == 'gpu':
            self.cuda()
            if hasattr(self, 'a_mean'):
                self.a_mean = self.a_mean.cuda()
                self.a_std = self.a_std.cuda()
                self.s_mean = self.s_mean.cuda()
                self.s_std = self.s_std.cuda()
        elif t == 'cpu':
            self.cpu()
            if hasattr(self, 'a_mean'):
                self.a_mean = self.a_mean.cpu()
                self.a_std = self.a_std.cpu()
                self.s_mean = self.s_mean.cpu()
                self.s_std = self.s_std.cpu()






class PolicyTEN(nn.Module):
    def __init__(self, opt):
        super(PolicyTEN, self).__init__()
        self.opt = opt
        self.past_encoder = encoder(opt, 0, opt.ncond)
        self.proj_past = nn.Linear(opt.hidden_size, opt.n_hidden)

        self.fc = nn.Sequential(
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden)
        )

        if opt.actions_subsample != -1:
            self.future_encoder = encoder(opt, 0, opt.actions_subsample)
            self.proj_future = nn.Linear(opt.hidden_size, opt.n_hidden)
            self.fc_z = nn.Sequential(
                nn.Linear(opt.n_hidden, opt.n_hidden),
                nn.ReLU(),
                nn.Linear(opt.n_hidden, opt.n_hidden),
                nn.ReLU(),
                nn.Linear(opt.n_hidden, self.opt.context_dim)
            )

            self.z_exp = nn.Sequential(
                nn.Linear(opt.context_dim, opt.n_hidden), 
                nn.ReLU(), 
                nn.Linear(opt.n_hidden, opt.n_hidden), 
                nn.ReLU(), 
                nn.Linear(opt.n_hidden, opt.n_hidden)
            )

        self.mu_net = nn.Linear(opt.n_hidden, opt.n_actions)
        self.logvar_net = nn.Linear(opt.n_hidden, opt.n_actions)

            
        self.cntr = 0
        self.p_z = []


    def save_z(self, z):
        if len(self.p_z) == 0:
            self.p_z = z.data.cpu()
        else:
            self.p_z = torch.cat((self.p_z, z.data.cpu()), 0)

    def sample(self):
        return Variable(random.choice(self.p_z).cuda().unsqueeze(0))

    def forward(self, input_images, input_states, target_images, target_states, sample=False, n_samples=1, save_z=False, dropout=0.0, normalize_inputs=False, normalize_outputs=False, std_mult=1.0):

        if normalize_inputs:
            input_images = input_images.clone().float().div_(255.0)
            input_states -= self.stats['s_mean'].view(1, 4).expand(input_states.size())
            input_states /= self.stats['s_std'].view(1, 4).expand(input_states.size())
            input_images = Variable(input_images.cuda()).unsqueeze(0)
            input_states = Variable(input_states.cuda()).unsqueeze(0)

        bsize = input_images.size(0)
        h_x = self.past_encoder(input_images, input_states)
        h_x = h_x.view(bsize, self.opt.hidden_size)
        h_x = self.proj_past(h_x)
        self.z = None

        if self.opt.actions_subsample == -1:
            h = h_x
        else:
            if self.cntr % self.opt.actions_subsample == 0:
                # sample new high-level action
                if not sample:
                    h_y = self.future_encoder(target_images.contiguous(), target_states.contiguous())
                    h_y = h_y.view(bsize, self.opt.hidden_size)
                    h_y = self.proj_future(h_y)
                    self.z = F.tanh(self.fc_z(h_x + h_y))
                    if save_z:
                        self.save_z(self.z)
                else:
                    self.z = self.sample()
            if random.random() < dropout:
                self.z = Variable(self.z.data.clone().zero_())
            h = h_x + self.z_exp(self.z)
        h = self.fc(h)
        mu = self.mu_net(h).view(bsize, self.opt.n_actions)
        logvar = self.logvar_net(h).view(bsize, self.opt.n_actions)
        logvar = torch.clamp(logvar, max = 4.0)
        std = logvar.mul(0.5).exp_()
        eps = Variable(torch.randn(bsize, n_samples, self.opt.n_actions).cuda())
        a = eps * std.view(bsize, 1, self.opt.n_actions) * std_mult
        a = a + mu.view(bsize, 1, self.opt.n_actions)
        entropy = torch.mean(std)
        self.cntr += 1

        if normalize_outputs:
            a = a.data
            a.clamp_(-3, 3)
            a *= self.stats['a_std'].view(1, 1, 2).expand(a.size()).cuda()
            a += self.stats['a_mean'].view(1, 1, 2).expand(a.size()).cuda()

        return a.squeeze(), entropy, mu, std, self.z



class PolicyVAE(nn.Module):
    def __init__(self, opt):
        super(PolicyVAE, self).__init__()
        self.opt = opt
        self.past_encoder = encoder(opt, 0, opt.ncond)
        self.proj_past = nn.Linear(opt.hidden_size, opt.n_hidden)

        self.fc = nn.Sequential(
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden)
        )

        if opt.actions_subsample != -1:
            self.future_encoder = encoder(opt, 0, opt.actions_subsample)
            self.proj_future = nn.Linear(opt.hidden_size, opt.n_hidden)
            self.fc_z = nn.Sequential(
                nn.Linear(opt.n_hidden, opt.n_hidden),
                nn.ReLU(),
                nn.Linear(opt.n_hidden, opt.n_hidden),
                nn.ReLU(),
                nn.Linear(opt.n_hidden, 2*self.opt.context_dim)
            )

            self.fc_z_prior = nn.Sequential(
                nn.Linear(opt.n_hidden, opt.n_hidden),
                nn.ReLU(),
                nn.Linear(opt.n_hidden, opt.n_hidden),
                nn.ReLU(),
                nn.Linear(opt.n_hidden, 2*self.opt.context_dim)
            )


            self.z_exp = nn.Sequential(
                nn.Linear(opt.context_dim, opt.n_hidden), 
                nn.ReLU(), 
                nn.Linear(opt.n_hidden, opt.n_hidden), 
                nn.ReLU(), 
                nn.Linear(opt.n_hidden, opt.n_hidden)
            )

        self.mu_net = nn.Linear(opt.n_hidden, opt.n_actions)
        self.logvar_net = nn.Linear(opt.n_hidden, opt.n_actions)
            
        self.cntr = 0
        self.p_z = []


    def save_z(self, z):
        if len(self.p_z) == 0:
            self.p_z = z.data.cpu()
        else:
            self.p_z = torch.cat((self.p_z, z.data.cpu()), 0)

    def reparameterize(self, mu, logvar, sample):
        if self.training or sample:
            std = logvar.mul(0.5).exp_()
            eps = Variable(std.data.new(std.size()).normal_())
            return eps.mul(std).add_(mu)
        else:
            return mu


    def forward(self, input_images, input_states, target_images, target_states, sample=False, n_samples=1, save_z=False, dropout=0.0, normalize_inputs=False, normalize_outputs=False):

        if normalize_inputs:
            input_images = input_images.clone().float().div_(255.0)
            input_states -= self.stats['s_mean'].view(1, 4).expand(input_states.size())
            input_states /= self.stats['s_std'].view(1, 4).expand(input_states.size())
            input_images = Variable(input_images.cuda()).unsqueeze(0)
            input_states = Variable(input_states.cuda()).unsqueeze(0)

        bsize = input_images.size(0)
        h_x = self.past_encoder(input_images, input_states)
        h_x = h_x.view(bsize, self.opt.hidden_size)
        h_x = self.proj_past(h_x)
        kld = Variable(torch.zeros(1).cuda())

        if self.opt.actions_subsample == -1:
            h = h_x
        else:
            if self.cntr % self.opt.actions_subsample == 0:
                # sample new high-level action
                mu_logvar_prior = self.fc_z_prior(h_x).view(bsize, self.opt.context_dim, 2)
                mu_prior = mu_logvar_prior[:, :, 0]
                logvar_prior = mu_logvar_prior[:, :, 1]

                if not sample:
                    h_y = self.future_encoder(target_images.contiguous(), target_states.contiguous())
                    h_y = h_y.view(bsize, self.opt.hidden_size)
                    h_y = self.proj_future(h_y)
                    mu_logvar = self.fc_z(h_x + h_y).view(bsize, self.opt.context_dim, 2)
                    mu = mu_logvar[:, :, 0]
                    logvar = mu_logvar[:, :, 1]
                    self.z = self.reparameterize(mu, logvar, sample=True)
                    kld = utils.kl_criterion(mu, logvar, mu_prior, logvar_prior)
                    if save_z:
                        self.save_z(self.z)
                else:
                    self.z = self.reparamaterize(mu_prior, logvar_prior, sample=True)
            if random.random() < dropout:
                self.z = Variable(self.z.data.clone().zero_())
            h = h_x + self.z_exp(self.z)
        h = self.fc(h)
        mu = self.mu_net(h).view(bsize, self.opt.n_actions)
        logvar = self.logvar_net(h).view(bsize, self.opt.n_actions)
        logvar = torch.clamp(logvar, max = 4.0)
        std = logvar.mul(0.5).exp_()
        eps = Variable(torch.randn(bsize, n_samples, self.opt.n_actions).cuda())
        a = eps * std.view(bsize, 1, self.opt.n_actions)
        a = a + mu.view(bsize, 1, self.opt.n_actions)
        entropy = torch.mean(std)
        self.cntr += 1

        if normalize_outputs:
            a = a.data
            a.clamp_(-3, 3)
            a *= self.stats['a_std'].view(1, 1, 2).expand(a.size()).cuda()
            a += self.stats['a_mean'].view(1, 1, 2).expand(a.size()).cuda()

        return a.squeeze(), kld, mu, std


        
        




class DeterministicPolicy(nn.Module):
    def __init__(self, opt, context_dim=0, output_dim=None):
        super(DeterministicPolicy, self).__init__()
        self.opt = opt
        self.encoder = encoder(opt, 0, opt.ncond)
        self.hsize = opt.nfeature*self.opt.h_height*self.opt.h_width
        self.n_outputs = opt.n_actions if output_dim is None else output_dim
        self.proj = nn.Linear(self.hsize, opt.n_hidden)
        self.context_dim = context_dim

        self.fc = nn.Sequential(
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, self.n_outputs)
        )

        if context_dim > 0:
            self.context_encoder = nn.Sequential(
                nn.Linear(context_dim, opt.n_hidden), 
                nn.ReLU(), 
                nn.Linear(opt.n_hidden, opt.n_hidden), 
                nn.ReLU(), 
                nn.Linear(opt.n_hidden, opt.n_hidden)
            )



    def forward(self, state_images, states, context=None, sample=True, normalize_inputs=False, normalize_outputs=False, n_samples=1):
        bsize = state_images.size(0)
        h = self.encoder(state_images, states).view(bsize, self.hsize)
        h = self.proj(h)
        if self.context_dim > 0:
            assert(context is not None)
            h = h + self.context_encoder(context)
        h = self.fc(h).view(bsize, self.n_outputs)
        return h


    def intype(self, t):
        if t == 'gpu':
            self.cuda()
        elif t == 'cpu':
            self.cpu()





class ValueFunction(nn.Module):
    def __init__(self, opt):
        super(ValueFunction, self).__init__()
        self.opt = opt
        self.encoder = encoder(opt, 0, opt.ncond)
        self.hsize = opt.nfeature*self.opt.h_height*self.opt.h_width
        self.n_outputs = 1
        self.proj = nn.Linear(self.hsize, opt.n_hidden)

        self.fc = nn.Sequential(
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.Dropout(p=opt.dropout, inplace=True),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.Dropout(p=opt.dropout, inplace=True),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.Dropout(p=opt.dropout, inplace=True),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, self.n_outputs)
        )


    def forward(self, state_images, states, context=None, sample=True, normalize_inputs=False, normalize_outputs=False, n_samples=1):
        bsize = state_images.size(0)
        h = self.encoder(state_images, states).view(bsize, self.hsize)
        h = self.proj(h)
        h = self.fc(h).view(bsize, self.n_outputs)
        return h


    def intype(self, t):
        if t == 'gpu':
            self.cuda()
        elif t == 'cpu':
            self.cpu()




# Mixture Density Network model
class PolicyMDN(nn.Module):
    def __init__(self, opt, n_mixture=10, npred=1):
        super(PolicyMDN, self).__init__()
        self.opt = opt
        self.npred = npred
        if not hasattr(opt, 'n_mixture'):
            self.opt.n_mixture = n_mixture
        self.encoder = encoder(opt, 0, opt.ncond)
        self.hsize = opt.nfeature*self.opt.h_height*self.opt.h_width
        self.n_outputs = self.npred*opt.n_actions
        self.fc = nn.Sequential(
            nn.Linear(self.hsize, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden),
            nn.ReLU(),
            nn.Linear(opt.n_hidden, opt.n_hidden)
        )

        self.pi_net = nn.Linear(opt.n_hidden, opt.n_mixture)
        self.mu_net = nn.Linear(opt.n_hidden, opt.n_mixture*self.n_outputs)
        self.sigma_net = nn.Linear(opt.n_hidden, opt.n_mixture*self.n_outputs)


    def forward(self, state_images, states, sample=False, normalize_inputs=False, normalize_outputs=False):

        if normalize_inputs:
            # policy network is trained with states normalized by mean and standard dev. 
            # this is to unnormalize the predictions at evaluation time. 
            state_images = state_images.clone().float().div_(255.0)
            states -= self.stats['s_mean'].view(1, 4).expand(states.size())
            states /= self.stats['s_std'].view(1, 4).expand(states.size())
            state_images = Variable(state_images.cuda()).unsqueeze(0)
            states = Variable(states.cuda()).unsqueeze(0)


        bsize = state_images.size(0)
        h = self.encoder(state_images, states).view(bsize, self.hsize)
        h = self.fc(h)
        # get parameters of output distribution
        pi = F.softmax(self.pi_net(h).view(bsize, self.opt.n_mixture), dim=1)
        mu = self.mu_net(h).view(bsize, self.opt.n_mixture, self.n_outputs)
        sigma = F.softplus(self.sigma_net(h)).view(bsize, self.opt.n_mixture, self.n_outputs)
        if sample:
            # pick a mixture component (one for each element in minibatch)
            k = torch.multinomial(pi, 1)
            a = []
            for b in range(bsize):
                # sample from Gaussian associated with those components
                a.append(torch.randn(self.npred, self.opt.n_actions).cuda()*sigma[b][k[b]].data.view(self.npred, self.opt.n_actions) + mu[b][k[b]].data.view(self.npred, self.opt.n_actions))
            a = torch.stack(a).squeeze()
            a = a.view(bsize, self.npred, 2)
        else:
            a = None

        if normalize_outputs:
            a *= self.stats['a_std'].view(1, 1, 2).expand(a.size()).cuda()
            a += self.stats['a_mean'].view(1, 1, 2).expand(a.size()).cuda()

        return pi, mu, sigma, a


    def intype(self, t):
        if t == 'gpu':
            self.cuda()
            if hasattr(self, 'a_mean'):
                self.a_mean = self.a_mean.cuda()
                self.a_std = self.a_std.cuda()
                self.s_mean = self.s_mean.cuda()
                self.s_std = self.s_std.cuda()
        elif t == 'cpu':
            self.cpu()
            if hasattr(self, 'a_mean'):
                self.a_mean = self.a_mean.cpu()
                self.a_std = self.a_std.cpu()
                self.s_mean = self.s_mean.cpu()
                self.s_std = self.s_std.cpu()
