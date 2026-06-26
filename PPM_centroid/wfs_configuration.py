import numpy as np

class Grating:
    
    def __init__(self,E0,fraction,g_dist,d_dist,pitch=None,travel=.02,name=None):
        self.E0 = E0
        self.fraction = fraction
        self.lambda0 = 1239.8/self.E0*1e-9
        self.g_dist = g_dist
        self.d_dist = d_dist
        self.name = name
        if pitch is None:
            self.pitch = self.calc_pitch()
        else:
            self.pitch = pitch
        self.fractions = np.array([1/6,1/4,1/3,1/2,2/3,3/4,5/6,1])
        self.mags = np.array([3,2,3,1,3,2,3,1])
        
        self.lows = np.zeros(np.shape(self.fractions))
        self.centers = np.zeros(np.shape(self.fractions))
        self.highs = np.zeros(np.shape(self.fractions))
        self.travel = travel

        
        for i in range(np.size(self.fractions)):
            self.lows[i], self.centers[i], self.highs[i] = self.calc_range(self.fractions[i])
            
        self.widths = self.highs-self.lows
        
    def calc_pitch(self):
        
        pitch = np.sqrt(self.g_dist*self.lambda0*(self.d_dist-self.g_dist)/self.fraction/self.d_dist/2)
        return pitch
    
    def calc_range(self,fraction):
        low = 1239.8/(2*fraction*self.pitch**2*self.d_dist/(self.g_dist+self.travel)/
                      (self.d_dist-(self.g_dist+self.travel)))*1e-9
        center = 1239.8/(2*fraction*self.pitch**2*self.d_dist/(self.g_dist)/(self.d_dist-(self.g_dist)))*1e-9
        high = 1239.8/(2*fraction*self.pitch**2*self.d_dist/(self.g_dist-self.travel)/
                       (self.d_dist-(self.g_dist-self.travel)))*1e-9
        return low, center, high
    
    # def plot_range(self,axis,color,label=None):
    #
    #     for i in range(np.size(self.fractions)):
    #         if i == 0:
    #             axis.plot(self.centers[i],0,linewidth=3,color=color,label=label)
    #             rect = patches.Rectangle((self.lows[i],0),self.widths[i],.5,color=color)
    #             axis.add_patch(rect)
    #         else:
    #             axis.plot(self.centers[i],0,linewidth=3,color=color)
    #             rect = patches.Rectangle((self.lows[i],0),self.widths[i],.5,color=color)
    #             axis.add_patch(rect)

class GratingCollection:
    def __init__(self, grating_list, name=None):

        for grating in grating_list:
            setattr(self, grating.name, grating)

        self.grating_list = grating_list
        self.name = name

        self.num_energies = 0
        for grating in grating_list:
            self.num_energies += len(grating.fractions) * 3
        self.energy_list = np.zeros(self.num_energies)
        num = 0
        for grating in grating_list:
            self.energy_list[num:num + 8] = grating.lows
            num += 8
            self.energy_list[num:num + 8] = grating.centers
            num += 8
            self.energy_list[num:num + 8] = grating.highs
            num += 8

    def find_configuration(self, energy):
        # find closest energy
        i1 = np.argmin(np.abs(energy - self.energy_list))
        # figure out which grating this is
        ig = int(i1 / 24)
        # figure out if low, center or high
        i_w = int((i1 - ig * 24) / 8)
        # figure out which fraction
        i_f = np.mod((i1 - ig * 24), 8)

        grating = self.grating_list[ig]
        print('Use {} {}'.format(self.name, grating.name))

        return_dict = {}

        if i_w == 0:
            print('closest energy: {:.0f}'.format(grating.lows[i_f]))
            print('low: move z towards positive limit')
            print('Talbot fraction: {}'.format(grating.mags[i_f]))
            return_dict['energy'] = grating.lows[i_f]
            return_dict['z'] = 30
            return_dict['fraction'] = grating.mags[i_f]
            #return_dict['message'] =
        elif i_w == 1:
            print('closest energy: {:.0f}'.format(grating.centers[i_f]))
            print('center: move z to center')
            print('Talbot fraction: {}'.format(grating.mags[i_f]))
            return_dict['energy'] = grating.centers[i_f]
            return_dict['z'] = 10
            return_dict['fraction'] = grating.mags[i_f]
        else:
            print('closest energy: {:.0f}'.format(grating.highs[i_f]))
            print('high: move z towards negative limit')
            print('Talbot fraction: {}'.format(grating.mags[i_f]))
            return_dict['energy'] = grating.highs[i_f]
            return_dict['z'] = -10
            return_dict['fraction'] = grating.mags[i_f]

        return return_dict

        

# IP1_target4 = Grating(1435,1/6,1.7707,2.587,pitch=35.8e-6,name='target4')
# IP1_target5 = Grating(1545,1/6,1.7707,2.587,pitch=34.6e-6,name='target5')
# IP2_target3 = Grating(540,1/3,0.9957,1.453,pitch=33.3e-6, name='target3')

# IP1_calc = GratingCollection([IP1_target4,IP1_target5],name='PF1K4')
# IP2_calc = GratingCollection([IP2_target3],name='PF2K4')
#
# # example output. The argument to "find_configuration" is the photon energy in eV.
# IP1_output = IP1_calc.find_configuration(350)
# IP2_output = IP2_calc.find_configuration(700)


